# Specs Documentation Index

Reference documentation for TRADE system architecture and specifications.

**Last Updated**: 2026-01-04

---

## Terminology Update (2026-01-04)

The following terminology changes are in progress:

| Old Term | New Term | Notes |
|----------|----------|-------|
| IdeaCard | Play | Complete strategy specification |
| configs/idea_cards/ | configs/plays/ | Strategy config directory |
| sandbox | forge | Development/validation environment |

**Trading Hierarchy** (Setup → Play → Playbook → System):
- **Setup**: Reusable rule blocks, filters, entry/exit logic
- **Play**: Complete strategy (formerly "IdeaCard")
- **Playbook**: Collection of plays for scenarios
- **System**: Full trading operation with risk/execution

See: `docs/architecture/LAYER_2_RATIONALIZATION_ARCHITECTURE.md` for complete details.

---

## Play & Blocks DSL

| Document | Purpose |
|----------|---------|
| [PLAY_SYNTAX.md](PLAY_SYNTAX.md) | Blocks DSL v3.0.0 syntax reference (12 operators, window ops) |
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

## Archived

Legacy documentation in `archived/`:
- `PLAY_ENGINE_FLOW_LEGACY.md` - Legacy signal_rules format (pre-blocks)
- `PLAY_OPERATORS_REFERENCE_LEGACY.md` - Legacy operators reference
- `PLAY_TRIGGER_AND_STRUCTURE_FLOW_LEGACY.md` - Legacy trigger/structure flow
- `MARKET_STRUCTURE_INTEGRATION_PROPOSAL.md` - Original market structure proposal
- `INTRADAY_ADAPTIVE_SYSTEM_REVIEW.md` - Adaptive system review
