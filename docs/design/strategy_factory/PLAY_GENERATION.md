# Play Generation: Strategy Conception at Scale

## Overview

Transform strategy ideas into hundreds or thousands of testable Play YAMLs
through templates, parameter grids, and AI-assisted generation.

## Three Generation Modes

### Mode 1: Template × Parameter Grid (Mechanical)

The simplest approach. Define a Play template with placeholders, define a
parameter grid, generate the cartesian product.

**Best for**: Optimizing a known strategy concept across parameter space.

```
1 template × 162 param combos = 162 plays
```

### Mode 2: AI-Assisted Generation (Creative)

Use the existing `forge-play` skill's knowledge of the Play DSL to generate
novel strategy concepts. Feed it:
- Trading methodology descriptions (ICT, Wyckoff, mean reversion)
- Market observations ("BTC tends to bounce off weekly VWAP")
- Indicator combinations to explore

**Best for**: Exploring new strategy concepts.

### Mode 3: Genetic Evolution (Iterative)

Start with a population of plays. Backtest them. Breed the winners
(crossover parameters, mutate values). Repeat.

**Best for**: Finding optimal parameters in a large search space.

---

## Template System

### Template Format

A Play YAML with `{param_name}` placeholders:

```yaml
# templates/rsi_mean_revert.yml
name: "rsi_revert_{rsi_length}_{rsi_ob}_{rsi_os}_{exec}"
description: "RSI mean reversion - factory generated"

symbol_universe: ["{symbol}"]

timeframes:
  low_tf: "{low_tf}"
  med_tf: "{med_tf}"
  high_tf: "{high_tf}"
  exec: "{exec}"

features:
  rsi:
    indicator: rsi
    params: { length: "{rsi_length}" }
    timeframe: exec
  ema_trend:
    indicator: ema
    params: { length: "{trend_ema}" }
    timeframe: med_tf

actions:
  entry_long:
    all:
      - [rsi, "<", "{rsi_os}"]
      - [ema_trend.slope, ">", 0]
  entry_short:
    all:
      - [rsi, ">", "{rsi_ob}"]
      - [ema_trend.slope, "<", 0]
  exit_long:
    any:
      - [rsi, ">", 50]
  exit_short:
    any:
      - [rsi, "<", 50]

risk:
  tp_pct: "{tp_pct}"
  sl_pct: "{sl_pct}"
  leverage: "{leverage}"
  initial_equity: 10000
```

### Grid Format

```yaml
# grids/rsi_mean_revert_grid.yml
template: rsi_mean_revert

# Fixed params (same for all plays)
fixed:
  symbol: BTCUSDT
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
  leverage: 1

# Variable params (generate combinations)
variable:
  rsi_length: [7, 14, 21]
  rsi_ob: [70, 75, 80]
  rsi_os: [20, 25, 30]
  trend_ema: [50, 100]
  exec: ["low_tf", "med_tf"]
  tp_pct: [2.0, 3.0, 5.0]
  sl_pct: [1.0, 1.5, 2.0]

# 3 × 3 × 3 × 2 × 2 × 3 × 3 = 972 combinations

# Optional: sampling
sampling:
  mode: random          # grid | random | latin_hypercube
  max_plays: 200        # Cap at 200 random samples
  seed: 42              # Reproducible sampling
```

### Constraint Rules

Some parameter combinations are invalid. Define constraints:

```yaml
constraints:
  - rule: "rsi_ob > rsi_os + 20"
    description: "Overbought must be well above oversold"
  - rule: "tp_pct > sl_pct"
    description: "TP must exceed SL for positive expectancy"
  - rule: "rsi_length <= 21 when exec == 'low_tf'"
    description: "Short RSI for fast timeframes"
```

---

## Generator Implementation

### Core Generator

```python
class StrategyGenerator:
    """Generate Play YAML files from templates and parameter grids."""

    def __init__(self, templates_dir: Path, grids_dir: Path, output_dir: Path):
        self.templates_dir = templates_dir
        self.grids_dir = grids_dir
        self.output_dir = output_dir

    def generate(self, grid_id: str) -> GenerationResult:
        """Generate all plays from a grid definition."""
        grid = self._load_grid(grid_id)
        template = self._load_template(grid.template)
        combinations = self._compute_combinations(grid)
        combinations = self._apply_constraints(combinations, grid.constraints)

        plays = []
        for combo in combinations:
            play_yaml = self._render_template(template, combo)
            play_id = self._derive_play_id(grid.template, combo)
            self._write_play(play_id, play_yaml)
            plays.append(play_id)

        return GenerationResult(
            grid_id=grid_id,
            template=grid.template,
            total_generated=len(plays),
            play_ids=plays,
        )

    def _compute_combinations(self, grid: Grid) -> list[dict]:
        """Compute parameter combinations based on sampling mode."""
        if grid.sampling.mode == "grid":
            return list(itertools.product(*grid.variable.values()))
        elif grid.sampling.mode == "random":
            full = list(itertools.product(*grid.variable.values()))
            rng = random.Random(grid.sampling.seed)
            return rng.sample(full, min(grid.sampling.max_plays, len(full)))
        elif grid.sampling.mode == "latin_hypercube":
            return self._latin_hypercube_sample(grid)
```

### Template Library (Starter Set)

| Template | Strategy Concept | Key Parameters |
|----------|-----------------|----------------|
| `ema_crossover` | EMA fast/slow cross | ema_fast, ema_slow, exec |
| `rsi_mean_revert` | RSI overbought/oversold | rsi_length, ob/os levels |
| `bb_squeeze` | Bollinger Band squeeze breakout | bb_length, bb_std, squeeze_threshold |
| `macd_momentum` | MACD crossover with trend | macd_fast, macd_slow, macd_signal |
| `vwap_revert` | VWAP mean reversion | vwap_band_mult, entry_threshold |
| `structure_break` | Market structure break + retest | swing_length, retest_tolerance |
| `multi_tf_confluence` | Multi-timeframe alignment | trend_tf, entry_tf, confirmation |

---

## AI-Assisted Generation

### Using forge-play Programmatically

The `forge-play` skill currently runs interactively. For factory use,
we need a programmatic variant:

```python
class AIStrategyGenerator:
    """Generate novel strategy concepts using LLM + Play DSL knowledge."""

    def generate_concepts(
        self,
        methodology: str,        # e.g., "ICT order blocks"
        num_variants: int = 10,
        indicators: list[str] | None = None,  # Constrain to available indicators
    ) -> list[PlayCandidate]:
        """Generate strategy concepts from a methodology description."""
        # 1. Load Play DSL reference
        # 2. Load available indicator list (44 indicators)
        # 3. Load available structure types (7 types)
        # 4. Prompt LLM to generate N Play YAML variants
        # 5. Validate each against schema
        # 6. Return valid candidates
```

### Knowledge Sources

```
knowledge/
├── methodologies/
│   ├── ict_concepts.md         # ICT: order blocks, FVG, liquidity
│   ├── wyckoff_phases.md       # Wyckoff: accumulation, distribution
│   ├── mean_reversion.md       # Statistical mean reversion
│   └── momentum.md             # Trend following, breakouts
│
├── market_observations/
│   ├── btc_patterns.md         # BTC-specific patterns
│   ├── funding_rate_edge.md    # Funding rate arbitrage
│   └── session_effects.md      # London/NY session patterns
│
└── indicator_combinations/
    ├── trend_filters.md        # Which indicators confirm trend
    ├── entry_triggers.md       # What signals work for entries
    └── exit_strategies.md      # TP/SL vs signal-based exits
```

---

## Genetic Evolution

### Population Lifecycle

```
Generation 0: Random population (100 plays)
    │
    ├── Backtest all 100
    ├── Score by fitness function
    ├── Select top 20 (tournament selection)
    │
    ├── Crossover: breed pairs → 40 offspring
    ├── Mutation: randomly perturb 10% of params
    ├── Immigration: 10 fresh random plays
    │
    └── Generation 1: 20 survivors + 40 offspring + 10 immigrants = 70
         │
         ├── Backtest all 70
         └── ... repeat for N generations
```

### Crossover Example

```python
def crossover(parent_a: dict, parent_b: dict) -> dict:
    """Single-point crossover of play parameters."""
    keys = sorted(parent_a.keys())
    split = random.randint(1, len(keys) - 1)

    child = {}
    for i, key in enumerate(keys):
        child[key] = parent_a[key] if i < split else parent_b[key]
    return child

# Parent A: ema_fast=8,  ema_slow=100, tp=2.0, sl=1.0
# Parent B: ema_fast=21, ema_slow=50,  tp=3.0, sl=0.5
# Split at index 2:
# Child:    ema_fast=8,  ema_slow=100, tp=3.0, sl=0.5
```

### Mutation Example

```python
def mutate(params: dict, mutation_rate: float = 0.1) -> dict:
    """Randomly perturb parameters."""
    mutated = params.copy()
    for key, value in mutated.items():
        if random.random() < mutation_rate:
            if isinstance(value, int):
                mutated[key] = value + random.choice([-1, 1]) * random.randint(1, 5)
            elif isinstance(value, float):
                mutated[key] = value * random.uniform(0.8, 1.2)
    return mutated
```

---

## Output Organization

### Factory Run Structure

```
plays/factory/
├── templates/                    # Reusable templates
│   ├── ema_crossover.yml
│   ├── rsi_mean_revert.yml
│   └── bb_squeeze.yml
│
├── grids/                        # Parameter grids
│   ├── ema_crossover_grid.yml
│   └── rsi_mean_revert_grid.yml
│
├── runs/                         # Generated play batches
│   ├── run_20260225_143000/
│   │   ├── manifest.json
│   │   ├── plays/
│   │   │   ├── ema_cross_8_50_low.yml
│   │   │   ├── ema_cross_8_50_med.yml
│   │   │   └── ... (162 plays)
│   │   └── results/
│   │       ├── backtest_synthetic.json
│   │       ├── backtest_real.json
│   │       └── live_sim.json
│   │
│   └── run_20260226_091500/
│       └── ...
│
└── winners/                      # Promoted plays (copied here)
    ├── ema_cross_12_100_low.yml
    └── rsi_revert_14_75_25_med.yml
```

### Manifest Schema

```json
{
  "run_id": "run_20260225_143000",
  "template": "ema_crossover",
  "grid": "ema_crossover_grid",
  "generation_mode": "grid",
  "total_generated": 162,
  "constraints_applied": 2,
  "plays_after_constraints": 148,
  "created_at": "2026-02-25T14:30:00",
  "stages": {
    "backtest_synthetic": {
      "status": "complete",
      "tested": 148,
      "passed": 45,
      "filter": "sharpe > 0.5"
    },
    "backtest_real": {
      "status": "complete",
      "tested": 45,
      "passed": 12,
      "filter": "sharpe > 1.0 AND max_dd < 20%"
    },
    "live_sim": {
      "status": "running",
      "active": 12,
      "started_at": "2026-02-25T16:00:00"
    }
  }
}
```

---

## CLI Interface

```bash
# Generate plays from a grid
python trade_cli.py factory generate --grid rsi_mean_revert_grid

# Generate with sampling
python trade_cli.py factory generate --grid rsi_mean_revert_grid --sample 200

# Run mass backtest on generated plays
python trade_cli.py factory backtest --run run_20260225_143000

# Filter results
python trade_cli.py factory filter --run run_20260225_143000 --min-sharpe 1.0

# Start live sim on survivors
python trade_cli.py factory live-sim --run run_20260225_143000 --top 20

# View leaderboard
python trade_cli.py factory status --run run_20260225_143000
```
