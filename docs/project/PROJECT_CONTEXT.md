# TRADE — Project Context

**Last Updated:** December 13, 2025

## Active Project

**The active project is the `TRADE/` folder.** This is the main trading bot project.

## Project Scope

- All development, features, and changes focus on the `TRADE/` directory
- The `trade_cli.py` file remains in the `TRADE/` root folder
- CLI functionality is the primary interface
- Tools layer (`src/tools/`) is the public API surface

---

## Current Focus: Backtest Engine (Refactor Complete — Phases 0–5)

The backtest engine is fully operational and refactor-complete with:
- **Modular exchange architecture**: Thin orchestrator with specialized modules (pricing, execution, funding, liquidation, ledger, metrics, constraints)
- Bybit-aligned accounting (isolated margin, USDT linear)
- Configurable risk profile (fees, leverage, stop conditions)
- Deterministic results (same inputs → same outputs)
- Canonical timing: `Bar.ts_open` (fills) + `Bar.ts_close` (step/eval)
- Canonical strategy input: `RuntimeSnapshot` only
- MTF/HTF caching with readiness gate
- Mark price unification (single mark per step)
- Preflight data health gate (tools) + bounded heal loop
- Artifact output (`result.json`, `trades.csv`, `equity.csv`, `account_curve.csv`, `run_manifest.json`, `events.jsonl`)
- Proof-grade metrics system (V2)

**See:** `docs/architecture/SIMULATED_EXCHANGE.md` for full accounting model & modular architecture

---

## Reference Folder

**`reference/exchanges/`** contains reference materials:

| Path | Contents |
|------|----------|
| `reference/exchanges/bybit/docs/v5/` | Official Bybit V5 API documentation |
| `reference/exchanges/pybit/` | Official pybit Python SDK source |

**When working on Bybit integration:**
- Consult `reference/exchanges/bybit/docs/v5/` for API endpoint details
- Reference `reference/exchanges/pybit/` for SDK usage patterns
- Check rate limit rules in `reference/exchanges/bybit/docs/v5/rate-limit/`

---

## Key Directories

| Directory | Purpose |
|-----------|---------|
| `src/tools/` | Public API surface (PRIMARY INTERFACE) |
| `src/backtest/` | Backtest engine |
| `src/core/` | Live trading logic |
| `src/data/` | Market data & DuckDB storage |
| `src/strategies/` | Base classes + system configs |
| `research/strategies/` | (Planned) Research strategy implementations |
| `data/backtests/` | Backtest artifacts |

---

## Development Rules

1. **All operations through tools** — Never call `bybit_client` directly
2. **No hardcoding** — Symbols, sizes, paths from config
3. **Safety first** — Risk manager checks before every order
4. **Demo first** — Test on demo API before live
5. **Reference docs first** — Check `reference/exchanges/` before implementing

---

## Documentation Structure

| Path | Contents |
|------|----------|
| `docs/architecture/` | Technical documentation |
| `docs/guides/` | How-to guides |
| `docs/project/` | Project documentation |
| `docs/examples/` | Code examples |
| `docs/brainstorm/` | Planning documents |

---

## Quick Reference

| Task | File |
|------|------|
| Run CLI | `python trade_cli.py` |
| System configs | `src/strategies/configs/*.yml` |
| Run backtest | `src/tools/backtest_tools.py` |
| Add strategy | `src/strategies/` (+ `src/strategies/registry.py`) |
| Check Bybit API | `reference/exchanges/bybit/docs/v5/` |
