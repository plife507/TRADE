# Specs Documentation Index

Reference documentation for TRADE system architecture and specifications.

**Last Updated**: 2026-01-04

---

## IdeaCard & Blocks DSL

| Document | Purpose |
|----------|---------|
| [IDEACARD_SYNTAX.md](IDEACARD_SYNTAX.md) | Blocks DSL v3.0.0 syntax reference (12 operators, window ops) |
| [IDEACARD_VISION.md](IDEACARD_VISION.md) | IdeaCard design vision: agent-ready, registry-based, fail-loud principles |

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

## Archived

Legacy documentation in `archived/`:
- `IDEACARD_ENGINE_FLOW_LEGACY.md` - Legacy signal_rules format (pre-blocks)
- `IDEACARD_OPERATORS_REFERENCE_LEGACY.md` - Legacy operators reference
- `IDEACARD_TRIGGER_AND_STRUCTURE_FLOW_LEGACY.md` - Legacy trigger/structure flow
- `MARKET_STRUCTURE_INTEGRATION_PROPOSAL.md` - Original market structure proposal
- `INTRADAY_ADAPTIVE_SYSTEM_REVIEW.md` - Adaptive system review
