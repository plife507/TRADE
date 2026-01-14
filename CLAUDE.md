# CLAUDE.md

Guidance for Claude when working with the TRADE trading bot.

## Prime Directives

**ALL FORWARD, NO LEGACY** - Delete old code, don't wrap it. No backward compatibility.

**MODERN PYTHON ONLY (3.12+)** - Type hints always, f-strings, pathlib, dataclasses, `X | None` not `Optional[X]`, `dict[str, int]` not `Dict`.

**LF LINE ENDINGS ONLY** - Use `open(file, 'w', newline='\n')` on Windows. Never CRLF.

**SEQUENTIAL DATABASE ACCESS** - DuckDB has no concurrent access. Run backtests sequentially.

**TODO-DRIVEN EXECUTION** - No code before TODO exists in `docs/todos/`. Every change maps to a checkbox.

**CLI-BASED VALIDATION** - Prefer CLI commands for validation. Python test infrastructure belongs in `src/forge/` modules. The `tests/` folder contains only Play YAML files for validation/stress testing.

## Project Overview

TRADE is a modular Bybit futures trading bot with backtest engine, USDT-only isolated margin.

**Trading Hierarchy:**
| Level | Name | Location |
|-------|------|----------|
| Block | Atomic reusable condition | `strategies/blocks/` |
| Play | Complete backtest-ready strategy | `strategies/plays/` |
| System | Multiple plays with regime blending | `strategies/systems/` |

**Promotion Path:** `src/forge/` (experimental) -> `strategies/plays/` (production)

## Architecture

```
TRADE/
├── src/
│   ├── backtest/          # Simulator engine (USDT-only, isolated margin)
│   │   ├── engine.py      # Backtest orchestrator
│   │   ├── sim/           # SimulatedExchange (pricing, execution, ledger)
│   │   ├── runtime/       # Snapshot, FeedStore, TFContext
│   │   ├── features/      # FeatureSpec, indicator computation
│   │   ├── incremental/   # O(1) structure detection
│   │   ├── rules/         # DSL compilation and evaluation
│   │   ├── rationalization/ # Layer 2: transitions, derived state
│   │   └── play/          # Play dataclass, config models
│   ├── forge/             # Development & validation environment
│   │   ├── validation/    # Test runners, fixtures, tier tests
│   │   ├── functional/    # Functional test infrastructure
│   │   ├── synthetic/     # Synthetic data harness and cases
│   │   └── audits/        # Audit tooling
│   ├── core/              # Live trading (risk, positions, orders)
│   ├── exchanges/         # Bybit API client
│   ├── data/              # DuckDB, market data
│   ├── tools/             # CLI/API surface (primary interface)
│   ├── viz/               # Backtest visualization (FastAPI + React)
│   └── utils/             # Logging, rate limiting, helpers
├── strategies/               # Blocks, Plays, Systems
├── tests/                 # Play YAML files ONLY (no Python)
│   ├── validation/plays/  # Validation Plays (V_100+)
│   ├── functional/plays/  # Functional test Plays
│   └── stress/plays/      # Stress test Plays
├── docs/todos/            # Work tracking (canonical)
└── trade_cli.py           # CLI entry point
```

## Quick Commands

```bash
python trade_cli.py                     # Interactive CLI
python trade_cli.py --smoke full        # Full smoke test
python trade_cli.py --smoke data_extensive  # Extensive data test
python trade_cli.py backtest metadata-smoke  # Indicator metadata test
```

## Domain Rules

### Backtest (`src/backtest/`)
- **USDT only**: Use `size_usdt`, never `size_usd`
- **Isolated margin only**: Reject `margin_mode="cross"`
- **Explicit indicators**: Undeclared indicators raise KeyError
- **Closed-candle only**: Indicators compute on closed bars, slower TFs forward-fill
- **O(1) hot loop**: Snapshot access must be O(1), no DataFrame ops

### Live Trading (`src/core/`, `src/exchanges/`)
- **API boundary**: All trades go through `src/tools/`, never `bybit_client` directly
- **Demo first**: Test in demo before live
- **Domain isolation**: Do NOT import from `src/backtest/`

### Data (`src/data/`)
- **Source of truth**: DuckDB for all historical data
- **Domain agnostic**: No trading logic, no execution semantics

### Tools (`src/tools/`)
- **Single entry point**: External callers use tools, not internal modules
- **ToolResult**: All tools return ToolResult with success/error

## Timeframe Definitions

**Valid Intervals:** `1m,3m,5m,15m,30m,1h,2h,4h,6h,12h,D,W,M` (8h is NOT valid)

| Category | Timeframes | Purpose |
|----------|------------|---------|
| LTF | 1m, 3m, 5m, 15m | Execution timing |
| MTF | 30m, 1h, 2h, 4h | Trade bias + structure |
| HTF | 6h, 12h, D | Trend, major levels |

**Hierarchy:** `HTF >= MTF >= LTF` (enforced by `validate_tf_mapping()`)

**Forward-Fill:** Slower TFs forward-fill until bar closes. No lookahead.

## Price Fields

| Field | Resolution | Use Case |
|-------|------------|----------|
| `last_price` | 1m | Signal evaluation |
| `mark_price` | 1m | PnL, liquidation, risk |
| `close` | exec_tf | Indicator computation |

## DSL Reference

**Canonical spec:** `docs/specs/PLAY_DSL_COOKBOOK.md`

**Operators:** `gt`, `lt`, `gte`, `lte`, `eq`, `cross_above`, `cross_below`, `between`, `near_abs`, `near_pct`, `in`

**Window operators:** `holds_for`, `occurred_within`, `count_true` (+ duration variants)

**Feature naming:** Use parameterized IDs (`ema_9`, `rsi_14`), never semantic (`ema_fast`)

## Structure Registry

| Type | Purpose | Key Outputs |
|------|---------|-------------|
| `swing` | Swing high/low | `high_level`, `low_level`, `version` |
| `fibonacci` | Fib levels | `level_<ratio>` |
| `zone` | Demand/supply | `state`, `upper`, `lower` |
| `trend` | Trend class | `direction`, `strength` |
| `derived_zone` | Fib zones from pivots | K slots + aggregates |

## Module Index

| Module | Purpose |
|--------|---------|
| `src/backtest/` | Simulator engine, 62-field metrics, 43 indicators |
| `src/forge/` | Play development, validation, audits, test infrastructure |
| `src/core/` | Live risk, positions, order execution |
| `src/exchanges/` | Bybit API wrapper |
| `src/data/` | DuckDB historical data store |
| `src/tools/` | CLI/API surface, ToolRegistry |
| `src/viz/` | TradingView-style visualization |

## Validation

**Validation Plays:** `tests/validation/plays/` (V_100+ format)

| Category | Purpose |
|----------|---------|
| V_100-V_106 | Core DSL (all/any/not, operators, windows) |
| V_115 | Type-safe operator validation |
| V_120-V_122 | Derived zones |
| V_130-V_133 | 1m action model |

**Tiers:**
- TIER 0: Quick check (<10 sec)
- TIER 1: Play normalization (ALWAYS FIRST)
- TIER 2: Audits (toolkit, rollup, metrics)
- TIER 3: Error case validation

## Agent Rules

- **Model selection**: Use `model="opus"` for coding agents
- **TODO-driven**: All work maps to `docs/todos/` checkboxes
- **Validation**: Run `validate` agent proactively during refactoring

## External References

| Topic | Location |
|-------|----------|
| DSL Cookbook | `docs/specs/PLAY_DSL_COOKBOOK.md` |
| Code examples | `docs/guides/CODE_EXAMPLES.md` |
| Engine concepts | `docs/guides/BACKTEST_ENGINE_CONCEPTS.md` |
| Environment vars | `env.example` |
| Work tracking | `docs/todos/TODO.md` |
| Bug tracker | `docs/audits/OPEN_BUGS.md` |

**Vendor refs:** `reference/exchanges/bybit/docs/v5/`, `reference/pandas_ta_repo/`
