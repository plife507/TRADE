# Architecture Documentation Index

Reference documentation for TRADE system architecture. These documents describe core design decisions, data flows, and implementation patterns.

---

## Active Documents

| Document | Purpose |
|----------|---------|
| [ARCH_SNAPSHOT.md](ARCH_SNAPSHOT.md) | System architecture overview: domains, runtime surfaces, invariants, accounting model |
| [ARCH_INDICATOR_WARMUP.md](ARCH_INDICATOR_WARMUP.md) | Indicator warmup computation, variable requirements, adding new indicators |
| [ARCH_DELAY_BARS.md](ARCH_DELAY_BARS.md) | Delay bars functionality, market structure configuration, evaluation start offset |
| [IDEACARD_ENGINE_FLOW.md](IDEACARD_ENGINE_FLOW.md) | IdeaCard field mappings through the backtest engine pipeline |
| [IDEACARD_VISION.md](IDEACARD_VISION.md) | IdeaCard design vision: agent-ready, registry-based, fail-loud principles |
| [INCREMENTAL_STATE_ARCHITECTURE.md](INCREMENTAL_STATE_ARCHITECTURE.md) | O(1) incremental state for market structure: primitives, registry, detectors, engine integration |

---

## Archived Documents

Historical proposals and reviews that informed current architecture but are no longer actively maintained.

| Document | Purpose |
|----------|---------|
| [archived/INTRADAY_ADAPTIVE_SYSTEM_REVIEW.md](archived/INTRADAY_ADAPTIVE_SYSTEM_REVIEW.md) | Design review of intraday adaptive trading system proposal |
| [archived/MARKET_STRUCTURE_INTEGRATION_PROPOSAL.md](archived/MARKET_STRUCTURE_INTEGRATION_PROPOSAL.md) | Integration proposal for market structure features (swings, pivots, trends) |
