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

1. **Interview** - Ask adaptive questions to gather: symbol, direction, timeframes, indicators, entry/exit conditions, risk parameters. Skip questions the user already answered in the seed prompt.

2. **Generate** - Write valid Play YAML using the DSL spec (`docs/PLAY_DSL_REFERENCE.md`). Save to `plays/{concept}/` folder with a `concept:` metadata tag.

3. **Validate** - Parse the play and run a synthetic smoke backtest. `--synthetic` reads the play's `synthetic:` block for pattern/bars/seed:
   ```bash
   python trade_cli.py backtest run --play <name> --synthetic
   ```

4. **Fix loop (human-in-the-loop)** - If validation fails: show the error, propose a fix as a diff, ask for approval before applying. Repeat until it passes or the user aborts.

5. **Post-create** - Ask what to do next (real-data backtest, create variants, tweak params, etc.)

## Concept Folders

| Folder | Strategy type |
|--------|--------------|
| `plays/mean_reversion/` | Oscillator extremes, revert to mean |
| `plays/trend_following/` | Ride momentum, trail stops |
| `plays/breakout/` | Range expansion, volume confirmation |
| `plays/scalping/` | Fast timeframe, tight risk |
| `plays/range_trading/` | Fade extremes within bounds |

## See Also

- `/backtest-smoke` - Quick smoke test for existing plays
- `/validate quick` - Full validation suite
- `docs/PLAY_DSL_REFERENCE.md` - Complete DSL syntax
