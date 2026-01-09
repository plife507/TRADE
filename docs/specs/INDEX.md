# Specs Documentation Index

Reference documentation for TRADE system architecture and specifications.

**Last Updated**: 2026-01-07

---

## Terminology (Current)

| Term | Description |
|------|-------------|
| Block | Atomic reusable condition (features + DSL condition) |
| Play | Complete backtest-ready strategy (features + actions + risk) |
| System | Multiple plays with regime-based weighted blending |

**Trading Hierarchy**: Block → Play → System

| Level | Location | Example |
|-------|----------|---------|
| Block | `strategies/blocks/` | ema_cross.yml |
| Play | `strategies/plays/` | I_001_ema.yml |
| System | `strategies/systems/` | (future) |

Validation Plays: `tests/validation/plays/`

---

## Play & Blocks DSL

| Document | Purpose |
|----------|---------|
| [PLAY_DSL_COOKBOOK.md](PLAY_DSL_COOKBOOK.md) | **Canonical** Play DSL syntax reference (operators, arithmetic, risk, MTF) |
| [PLAY_VISION.md](PLAY_VISION.md) | Play design vision: agent-ready, registry-based, fail-loud principles |

---

## Core Architecture

| Document | Purpose |
|----------|---------|
| [ARCH_SNAPSHOT.md](ARCH_SNAPSHOT.md) | System architecture overview: domains, runtime surfaces, invariants |
| [ARCH_INDICATOR_WARMUP.md](ARCH_INDICATOR_WARMUP.md) | Indicator warmup computation, variable requirements |
| [ARCH_DELAY_BARS.md](ARCH_DELAY_BARS.md) | Delay bars functionality, market structure configuration |

---

## Execution & Order Management

| Document | Purpose |
|----------|---------|
| [LIMIT_ORDERS_AND_SCALING.md](LIMIT_ORDERS_AND_SCALING.md) | **Future Phase**: Limit orders, position scaling, fill simulation, live parity |

---

## Incremental State (O(1) Hot Loop)

| Document | Purpose |
|----------|---------|
| [INCREMENTAL_STATE_ARCHITECTURE.md](INCREMENTAL_STATE_ARCHITECTURE.md) | O(1) incremental state: 6 structure detectors, primitives, registry |
| [DERIVATION_RULE_INVESTIGATION.md](DERIVATION_RULE_INVESTIGATION.md) | K slots + aggregates pattern for derived zones (Phase 12) |

---

## The Forge (src/forge/)

The Forge is the development and validation environment where strategy components are built and hardened before production use. See `LAYER_2_RATIONALIZATION_ARCHITECTURE.md` Section 10 for complete details.

Key concepts:
- **Seed Data**: Deterministic test inputs for math proof validation
- **Audits**: Contract validation (indicators, structures, rollups, artifacts)
- **Promotion Path**: Forge → Math Proven → Registered → Market Tested → Production

---

## DSL Strategy Patterns

See `docs/guides/DSL_STRATEGY_PATTERNS.md` for 7 documented patterns:
1. Momentum Confirmation (holds_for_duration)
2. Dip Buying / Mean Reversion (occurred_within_duration)
3. Multi-Timeframe Confirmation (anchor_tf)
4. Breakout with Volume Confirmation (count_true_duration)
5. Price Action Crossovers (last_price + cross_above/below)
6. Cooldown / Anti-Chop Filter (occurred_within)
7. Exhaustion Detection (count_true + trend)
