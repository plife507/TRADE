"""
Shadow Exchange (M4) — The Training Ground.

Runs proven plays against real market data using SimExchange for order
execution. NOT demo mode — unlimited parallelism, full accounting,
real WS prices, known fidelity gaps.

Modules:
- engine: ShadowEngine (per-play: PlayEngine + SimExchange)
- orchestrator: ShadowOrchestrator (multi-play lifecycle manager)
- feed_hub: SharedFeedHub (one WS per symbol, fan-out to N engines)
- journal: ShadowJournal (JSONL trade + snapshot logging)
- performance_db: ShadowPerformanceDB (DuckDB long-term tracking)
- types: Core dataclasses (slots-optimized for 50+ engines)
- config: ShadowConfig, ShadowPlayConfig
"""
