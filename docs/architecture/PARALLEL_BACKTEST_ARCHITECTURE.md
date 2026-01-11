# Parallel Backtest Architecture for Evolutionary Learning

> **Created**: 2026-01-10 | **Status**: Future Reference | **Purpose**: GA/Evolution system planning

---

## Overview

This document outlines the architecture for running tens of thousands of backtests in parallel for evolutionary learning (genetic algorithms) to explore DSL parameter space.

---

## The Challenge

**Goal**: Run 10,000+ backtests exploring different indicator/structure combinations on the same market data.

**Constraint**: DuckDB does NOT support concurrent access (per CLAUDE.md prime directive).

**Solution**: Decouple data loading from backtest execution.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  SHARED DATA LAYER (read-only, multi-access)           │
│  ─────────────────────────────────────────────────────  │
│  SOLUSDT 1Y OHLCV  │  BTCUSDT Bear 2022  │  Bull 2024  │
│                                                         │
│  Options:                                               │
│  • Parquet files (native concurrent reads)              │
│  • Arrow shared memory (zero-copy)                      │
│  • Pre-loaded DataFrames (copy to workers)              │
└─────────────────────────────────────────────────────────┘
            ↓                   ↓                 ↓
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│ Worker 1      │  │ Worker 2      │  │ Worker 3      │
│ EMA+RSI+Zones │  │ MACD+BBands   │  │ SuperTrend    │
│ compute indic │  │ compute indic │  │ compute indic │
│ run backtest  │  │ run backtest  │  │ run backtest  │
└───────────────┘  └───────────────┘  └───────────────┘
            ↓                   ↓                 ↓
┌─────────────────────────────────────────────────────────┐
│  RESULTS AGGREGATION                                    │
│  ─────────────────────────────────────────────────────  │
│  Fitness scores → Selection → Mutation → Next Gen      │
└─────────────────────────────────────────────────────────┘
```

---

## Key Insight

Each backtest varies the **indicator/structure mix**, NOT the underlying OHLCV data. Therefore:

1. Load raw OHLCV once (serial, from DuckDB)
2. Export to Parquet or hold in memory
3. Close DuckDB connection
4. Each worker computes its OWN indicators based on Play config
5. Workers run hot loop in parallel
6. Aggregate results

---

## Data Access Options

| Approach | Pros | Cons |
|----------|------|------|
| **Parquet files** | Native concurrent reads, fast columnar | Extra export step |
| **DuckDB read-only** | Already have it, `read_only=True` mode | May still have lock issues |
| **Arrow shared memory** | Zero-copy, fastest | More complex setup |
| **Load once → copy** | Simplest | Memory per worker |

**Recommended**: Parquet files for "datasets" (SOLUSDT 1Y, Bear Market 2022, etc.)

---

## Resource Requirements

### Single Backtest Profile (4Y @ 15m, ~140k bars)

| Component | Estimate |
|-----------|----------|
| Raw OHLCV | ~2 MB per symbol/tf |
| Indicators (10-20) | ~3-5 MB |
| FeedStore + Python overhead | ~5-10 MB |
| **Total memory per run** | **~15-30 MB** |
| **CPU** | 1 core (hot loop single-threaded) |

### Complexity Levels

| Level | Name | Indicators | Structures | TFs | Mem/Run | CPU/Run |
|-------|------|------------|------------|-----|---------|---------|
| 1 | Trivial | 2 | 0 | 1 | 20 MB | 0.5s |
| 2 | Minimal | 4 | 0 | 1 | 25 MB | 0.8s |
| 3 | Basic | 6 | 1 | 1 | 35 MB | 1.2s |
| 4 | Light | 8 | 1 | 2 | 50 MB | 2.0s |
| 5 | Standard | 12 | 2 | 2 | 70 MB | 3.5s |
| 6 | Moderate | 15 | 2 | 3 | 100 MB | 5.0s |
| 7 | Advanced | 20 | 3 | 3 | 140 MB | 8.0s |
| 8 | Heavy | 25 | 4 | 3 | 200 MB | 12s |
| 9 | Complex | 30 | 5 | 3 | 280 MB | 18s |
| 10 | Maximum | 40+ | 6 | 4 | 400 MB | 30s |

### Multi-Timeframe Overhead

| Config | Indicators | Structures | TFs | Mem/Run | CPU/Run |
|--------|------------|------------|-----|---------|---------|
| MTF Light | 6/TF (18) | 1 | 3 | 120 MB | 4s |
| MTF Standard | 10/TF (30) | 2 | 3 | 200 MB | 7s |
| MTF Advanced | 15/TF (45) | 3 | 3 | 350 MB | 12s |
| MTF Heavy | 20/TF (60) | 4 | 3 | 500 MB | 20s |
| MTF Full | 15/TF (60) | 4 | 4 | 700 MB | 30s |

---

## Hardware Scaling

### Development Machine (Ryzen 7 8845HS, 32 GB RAM)

| Complexity | Parallel Workers | 10k Backtests Time |
|------------|------------------|---------------------|
| Lvl 1-2 | 14 | 6-10 min |
| Lvl 3-4 | 14 | 15-25 min |
| Lvl 5 | 14 | 40 min |
| Lvl 6 | 12 | 70 min |
| Lvl 7 | 10 | 2 hours |
| MTF Standard | 10 | 2 hours |
| MTF Heavy | 6 | 9 hours |

### Cloud Scaling

| Instance | Cores | RAM | Cost/hr | Lvl 5 10k | MTF Std 10k |
|----------|-------|-----|---------|-----------|-------------|
| c6i.8xlarge | 32 | 64 GB | ~$1.36 | 18 min | 36 min |
| c6i.16xlarge | 64 | 128 GB | ~$2.72 | 9 min | 18 min |
| c6i.24xlarge | 96 | 192 GB | ~$4.08 | 6 min | 12 min |
| c6i.32xlarge | 128 | 256 GB | ~$5.44 | 5 min | 9 min |

---

## GA Configuration Recommendations

### For Development Machine

| Parameter | Value |
|-----------|-------|
| Population size | 100-200 |
| Generations | 50-100 |
| Total evaluations | 5k-20k |
| Workers | 12 (leave 4 threads for OS) |
| Complexity | Level 4-6 |
| Execution TF | 15m or 1h |

### Estimated Runtimes

| Config | Evaluations | Time |
|--------|-------------|------|
| 100 pop × 50 gen | 5,000 | ~25 min @ Lvl 5 |
| 200 pop × 100 gen | 20,000 | ~2.5 hrs @ Lvl 5 |
| 200 pop × 100 gen | 20,000 | ~4 hrs @ MTF Std |

---

## Implementation Components

### 1. DataPreloader

```python
class DataPreloader:
    """Pre-load market data for parallel backtest consumption."""

    def __init__(self, symbols: list[str], timeframes: list[str], period: str):
        self.symbols = symbols
        self.timeframes = timeframes
        self.period = period
        self._data: dict[tuple[str, str], pd.DataFrame] = {}

    def load_all(self) -> None:
        """Load from DuckDB, then close connection."""
        store = get_historical_store("live")
        for symbol in self.symbols:
            for tf in self.timeframes:
                df = store.get_ohlcv(symbol, tf, period=self.period)
                self._data[(symbol, tf)] = df
        store.close()

    def export_to_parquet(self, output_dir: Path) -> None:
        """Export datasets for worker access."""
        for (symbol, tf), df in self._data.items():
            path = output_dir / f"{symbol}_{tf}.parquet"
            df.to_parquet(path)

    def get_data(self, symbol: str, tf: str) -> pd.DataFrame:
        return self._data[(symbol, tf)]
```

### 2. ParallelBacktestRunner

```python
from concurrent.futures import ProcessPoolExecutor

class ParallelBacktestRunner:
    """Run backtests in parallel using ProcessPoolExecutor."""

    def __init__(self, max_workers: int = 12):
        self.max_workers = max_workers

    def run_batch(
        self,
        play_configs: list[PlayConfig],
        data_path: Path
    ) -> list[BacktestMetrics]:
        with ProcessPoolExecutor(max_workers=self.max_workers) as pool:
            futures = [
                pool.submit(self._run_single, config, data_path)
                for config in play_configs
            ]
            return [f.result() for f in futures]

    @staticmethod
    def _run_single(config: PlayConfig, data_path: Path) -> BacktestMetrics:
        # Load from Parquet (no DuckDB access)
        df = pd.read_parquet(data_path / f"{config.symbol}_{config.tf}.parquet")

        # Build FeedStore with config-specific indicators
        feed = build_feed_from_config(df, config)

        # Run backtest (hot loop only)
        engine = BacktestEngine(config)
        engine.set_prebuilt_feed(feed)
        return engine.run()
```

### 3. GeneticOptimizer

```python
class GeneticOptimizer:
    """Evolutionary search over Play configurations."""

    def __init__(
        self,
        population_size: int = 100,
        generations: int = 50,
        mutation_rate: float = 0.1
    ):
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.runner = ParallelBacktestRunner()

    def evolve(self, data_path: Path) -> PlayConfig:
        population = self._initialize_population()

        for gen in range(self.generations):
            # Evaluate fitness in parallel
            metrics = self.runner.run_batch(population, data_path)
            fitness_scores = [self._calculate_fitness(m) for m in metrics]

            # Select and mutate
            population = self._select_and_mutate(population, fitness_scores)

        return self._best_individual(population, fitness_scores)
```

---

## Dataset Concepts

Define named datasets for different market conditions:

| Dataset | Period | Characteristics |
|---------|--------|-----------------|
| `BTCUSDT_FULL_CYCLE` | 2021-2024 | Bull → Bear → Recovery |
| `BTCUSDT_BEAR_2022` | 2022 | Strong downtrend |
| `BTCUSDT_BULL_2024` | 2024 | Strong uptrend |
| `SOLUSDT_VOLATILE` | 2023-2024 | High volatility periods |
| `ETHUSDT_RANGE` | Selected | Sideways consolidation |

This enables testing strategies against specific market regimes.

---

## Files to Create/Modify

| File | Purpose |
|------|---------|
| `src/forge/data_preloader.py` | NEW: Batch data loading |
| `src/forge/parallel_runner.py` | NEW: ProcessPoolExecutor wrapper |
| `src/forge/genetic_optimizer.py` | NEW: GA framework |
| `src/backtest/engine.py` | MODIFY: Accept pre-built FeedStore |
| `src/backtest/runtime/feed_store.py` | MODIFY: Add serialization |
| `src/tools/backtest_tools.py` | MODIFY: Add GA entry point |

---

## Recommended Approach

### Phase 1: Foundation
1. Implement `DataPreloader` with Parquet export
2. Modify engine to accept pre-built data
3. Create `ParallelBacktestRunner`

### Phase 2: GA Framework
1. Implement `GeneticOptimizer`
2. Define mutation operators for Play configs
3. Define fitness functions (Sharpe, Sortino, etc.)

### Phase 3: Datasets
1. Create named dataset definitions
2. Build dataset catalog (market regimes)
3. Add CLI for dataset management

### Phase 4: Cloud Integration
1. Add cloud burst capability
2. Results aggregation across nodes
3. Checkpoint/resume for long runs

---

## Sweet Spot Configuration

For iterative development on local machine:

```yaml
# Recommended GA config for Ryzen 7 + 32 GB
population_size: 150
generations: 50
workers: 12
complexity: Level 5 (Standard)
execution_tf: 15m
timeframes: [15m, 1h, 4h]
dataset: BTCUSDT_FULL_CYCLE

# Expected runtime: ~1 hour for full evolution
# Total evaluations: 7,500
```
