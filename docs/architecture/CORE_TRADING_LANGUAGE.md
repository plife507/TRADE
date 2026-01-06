# Core Trading Language Architecture

> **The Play is the universal contract.**
> Human, Agent, or ML - all speak the same language.

---

## The Vision

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         THREE INPUT MODES                                   │
│                     (Same Output: Play YAML)                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │   HUMAN         │  │   AGENT         │  │   EVOLUTION     │             │
│  │   (Hand-coded)  │  │   (LLM Swarm)   │  │   (ML/GA/RL)    │             │
│  ├─────────────────┤  ├─────────────────┤  ├─────────────────┤             │
│  │ Write YAML      │  │ Debate → YAML   │  │ Mutate → YAML   │             │
│  │ directly        │  │ consensus       │  │ fitness test    │             │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘             │
│           │                    │                    │                       │
│           └────────────────────┼────────────────────┘                       │
│                                │                                            │
│                                ▼                                            │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                         PLAY YAML                                 │  │
│  │                   (The Core Trading Language)                         │  │
│  │                                                                       │  │
│  │   • features: [indicators, structures]                                │  │
│  │   • variables: [named conditions]                                     │  │
│  │   • blocks: [entry, exit, risk rules]                                 │  │
│  │   • execution: [sizing, TP/SL, order types]                           │  │
│  │                                                                       │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                │                                            │
│                                ▼                                            │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                      UNIFIED ENGINE                                   │  │
│  │              (Simulator / Demo / Live - Same Code)                    │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Why Play is the Universal Contract

### The Punch Card Analogy

```
1960s: Punch Card → Compiler → Machine Code → Computer
2026:  Play  → Engine   → Orders      → Exchange
```

**The punch card abstracted hardware.** You didn't need to know the CPU architecture - you wrote your program in a standard format, and the system handled the rest.

**The Play abstracts trading.** You don't need to know:
- How indicators are computed (vectorized vs incremental)
- How orders are executed (simulated vs real)
- How state is buffered (ring buffers vs deques)
- How agents reach consensus

You just write the trading idea in the Core Trading Language.

### Three Authors, One Language

| Author | How They Create | What They Produce |
|--------|-----------------|-------------------|
| **Human** | Write YAML by hand | Play |
| **Agent Swarm** | Debate → consensus → YAML | Play |
| **Evolution** | Mutate → test → select → YAML | Play |

**The engine doesn't care who wrote it.** It only cares that the YAML is valid.

---

## The Core Trading Language (CTL)

### Language Elements

```yaml
# ============================================================
# PLAY: The Core Trading Language
# ============================================================

# 1. IDENTITY
name: "zone_breakout_v3"
version: "3.1.0"
author: "agent_swarm"  # or "human" or "evolution_gen_42"

# 2. MARKET CONTEXT
symbol: "BTCUSDT"
tf: "15m"              # Execution timeframe
mtf: "1h"              # Optional mid timeframe
htf: "4h"              # Optional high timeframe

# 3. FEATURES (What to observe)
features:
  # Indicators - vectorized precompute
  - type: ema
    id: ema_fast
    params: { length: 21, source: close }

  - type: supertrend
    id: st
    params: { length: 10, multiplier: 3.0 }

  # Structures - incremental per-bar
  - type: swing
    id: swing
    tf: exec
    params: { left: 5, right: 5 }

  - type: derived_zone
    id: demand
    tf: exec
    depends_on: { swing: swing }
    params:
      levels: [0.618, 0.786]
      mode: retracement
      max_active: 3

# 4. VARIABLES (Named conditions - reusable)
variables:
  trend_up:
    lhs: { feature_id: st, field: direction }
    op: eq
    rhs: 1

  zone_active:
    lhs: { feature_id: demand, field: any_active }
    op: eq
    rhs: true

  price_near_zone:
    lhs: { builtin: close }
    op: near_pct
    rhs: { feature_id: demand, field: closest_active_upper }
    tolerance: 0.5

# 5. BLOCKS (Control flow - first-match semantics)
blocks:
  - id: entry
    cases:
      - when:
          all:
            - var: trend_up
            - var: zone_active
            - var: price_near_zone
        emit:
          - action: entry_long
            metadata:
              size_pct: 0.10
              stop_loss_ref: { feature_id: demand, field: closest_active_lower }
              take_profit_ref: { feature_id: swing, field: high_level }

  - id: exit
    cases:
      - when:
          any:
            - lhs: { feature_id: demand, field: any_touched }
              op: eq
              rhs: true
        emit:
          - action: exit_long
            metadata:
              size_pct: 0.5  # Partial exit

# 6. EXECUTION (How to trade)
execution:
  initial_equity: 10000
  risk_per_trade_pct: 2.0
  max_leverage: 10.0
  slippage_bps: 5.0
```

### Language Semantics

| Element | Semantics | Evaluation |
|---------|-----------|------------|
| `features` | WHAT to observe | Precomputed or incremental |
| `variables` | Named BOOLEAN conditions | Evaluated per snapshot |
| `blocks` | WHEN → WHAT actions | First-match, deterministic |
| `execution` | HOW to size/execute | Applied to emitted intents |

---

## State Buffering Architecture

### Current State (What You Have)

```python
# HistoryManager - Rolling windows of snapshots
class HistoryManager:
    _history_bars_exec: list[Bar]           # Last N exec bars
    _history_features_exec: list[Snapshot]  # Last N exec features
    _history_features_htf: list[Snapshot]   # Last N HTF features
    _history_features_mtf: list[Snapshot]   # Last N MTF features

# MonotonicDeque - O(1) sliding min/max
class MonotonicDeque:
    def push(self, idx: int, value: float): ...
    def get(self) -> float | None: ...

# RingBuffer - O(1) fixed-size lookback
class RingBuffer:
    def push(self, value: float): ...
    def __getitem__(self, idx: int) -> float: ...
```

### What's Needed: Universal State Buffer

```python
# ============================================================
# UNIVERSAL STATE BUFFER
# ============================================================
#
# Any feature (indicator or structure) can request history.
# The buffer provides O(1) access to any depth.

@dataclass
class StateBuffer:
    """
    Universal state buffer for all features.

    Every feature_id gets its own ring buffer.
    Depth is dynamic based on what strategies request.
    """

    # Feature state: feature_id → field → RingBuffer
    _buffers: dict[str, dict[str, RingBuffer]]

    # Dynamic depth: feature_id → field → requested_depth
    _depths: dict[str, dict[str, int]]

    def register(self, feature_id: str, field: str, depth: int) -> None:
        """Register a feature field with requested history depth."""
        if feature_id not in self._buffers:
            self._buffers[feature_id] = {}
            self._depths[feature_id] = {}

        current_depth = self._depths[feature_id].get(field, 0)
        if depth > current_depth:
            # Expand buffer
            self._depths[feature_id][field] = depth
            self._buffers[feature_id][field] = RingBuffer(depth)

    def push(self, feature_id: str, field: str, value: float) -> None:
        """Push new value to feature buffer."""
        if feature_id in self._buffers and field in self._buffers[feature_id]:
            self._buffers[feature_id][field].push(value)

    def get(self, feature_id: str, field: str, offset: int = 0) -> float:
        """
        Get value at offset (0 = current, 1 = previous, etc.)

        Args:
            feature_id: The feature identifier (e.g., "ema_fast")
            field: The field name (e.g., "value", "direction")
            offset: How many bars back (0 = current)

        Returns:
            The value at the requested offset
        """
        buffer = self._buffers[feature_id][field]
        # Convert offset to ring buffer index
        # offset=0 → newest, offset=1 → second newest, etc.
        idx = len(buffer) - 1 - offset
        return buffer[idx]

    def get_window(self, feature_id: str, field: str, size: int) -> np.ndarray:
        """Get last N values as numpy array."""
        buffer = self._buffers[feature_id][field]
        return buffer.to_array()[-size:]
```

### DSL Access to History

```yaml
# Play can access history via offset
variables:
  ema_crossed_above:
    # Current EMA > Previous EMA AND Previous EMA <= 2-bars-ago EMA
    all:
      - lhs: { feature_id: ema_fast, field: value, offset: 0 }
        op: gt
        rhs: { feature_id: ema_slow, field: value, offset: 0 }
      - lhs: { feature_id: ema_fast, field: value, offset: 1 }
        op: lte
        rhs: { feature_id: ema_slow, field: value, offset: 1 }

  # Window operators automatically request depth
  held_above_zone_5_bars:
    lhs: { feature_id: demand, field: any_active }
    op: holds_for
    rhs: true
    bars: 5  # Implicitly requests 5-bar depth
```

### Auto-Registration from Play

```python
def build_state_buffer_from_play(card: Play) -> StateBuffer:
    """
    Analyze Play to determine required buffer depths.

    Scans all variables and blocks for:
    - Explicit offset references (offset: N)
    - Window operators (holds_for, occurred_within)
    - Cross operators (need offset: 1)
    """
    buffer = StateBuffer()

    # Scan all expressions for offset requirements
    for var in card.variables:
        depths = extract_depth_requirements(var.expr)
        for feature_id, field, depth in depths:
            buffer.register(feature_id, field, depth)

    for block in card.blocks:
        for case in block.cases:
            depths = extract_depth_requirements(case.when)
            for feature_id, field, depth in depths:
                buffer.register(feature_id, field, depth)

    # Cross operators implicitly need depth=2
    if uses_cross_operators(card):
        for feature_id, field in get_cross_features(card):
            buffer.register(feature_id, field, max(2, buffer.get_depth(feature_id, field)))

    return buffer
```

---

## Playbooks: Composing Plays

### The Hierarchy

```
Play     → Single trading idea (one entry/exit logic)
Playbook     → Collection of Plays (market regime aware)
Strategy     → Playbook + capital allocation + risk budget
```

### Playbook Example

```yaml
# ============================================================
# PLAYBOOK: Multi-Regime BTC Strategy
# ============================================================

name: "btc_all_weather"
version: "1.0.0"

# Capital allocation across ideas
allocation:
  mode: "regime_switch"  # or "parallel", "sequential"
  total_capital: 100000

# Regime detection (meta-Play)
regime_detector:
  type: play
  path: "regimes/volatility_regime.yml"
  # Emits: { regime: "low_vol" | "high_vol" | "trending" | "ranging" }

# Plays per regime
ideas:
  low_vol:
    - path: "ideas/mean_reversion_tight.yml"
      weight: 0.6
    - path: "ideas/grid_accumulate.yml"
      weight: 0.4

  high_vol:
    - path: "ideas/breakout_momentum.yml"
      weight: 0.7
    - path: "ideas/volatility_scalp.yml"
      weight: 0.3

  trending:
    - path: "ideas/trend_follow_pyramiding.yml"
      weight: 0.8
    - path: "ideas/pullback_entries.yml"
      weight: 0.2

  ranging:
    - path: "ideas/zone_fade.yml"
      weight: 0.5
    - path: "ideas/range_breakout.yml"
      weight: 0.5

# Risk coordination across ideas
risk_coordination:
  max_total_exposure_pct: 80
  max_correlation: 0.7
  max_ideas_active: 3
```

### Playbook Executor

```python
class PlaybookExecutor:
    """
    Executes multiple Plays based on regime.

    Coordinates capital allocation and risk across ideas.
    """

    def __init__(self, playbook: Playbook):
        self.playbook = playbook
        self.regime_detector = load_play(playbook.regime_detector.path)
        self.ideas: dict[str, list[Play]] = {}

        for regime, idea_configs in playbook.ideas.items():
            self.ideas[regime] = [
                load_play(cfg.path) for cfg in idea_configs
            ]

    async def on_bar(self, snapshot: RuntimeSnapshotView) -> list[Intent]:
        """
        Process bar across all active ideas.

        1. Detect current regime
        2. Activate/deactivate ideas based on regime
        3. Execute active ideas
        4. Coordinate risk across ideas
        """
        # 1. Detect regime
        regime_intents = self.regime_executor.execute(snapshot)
        current_regime = self._extract_regime(regime_intents)

        # 2. Get active ideas for regime
        active_ideas = self.ideas.get(current_regime, [])

        # 3. Execute each idea
        all_intents: list[Intent] = []
        for idea in active_ideas:
            intents = idea.executor.execute(snapshot)
            all_intents.extend(intents)

        # 4. Coordinate risk
        coordinated = self._coordinate_risk(all_intents, snapshot)

        return coordinated

    def _coordinate_risk(
        self,
        intents: list[Intent],
        snapshot: RuntimeSnapshotView,
    ) -> list[Intent]:
        """
        Apply cross-idea risk limits.

        - Max total exposure
        - Max correlated positions
        - Max ideas active
        """
        # Filter intents that would exceed limits
        filtered = []
        current_exposure = snapshot.total_exposure_pct

        for intent in intents:
            intent_exposure = self._estimate_exposure(intent)
            if current_exposure + intent_exposure <= self.playbook.risk_coordination.max_total_exposure_pct:
                filtered.append(intent)
                current_exposure += intent_exposure

        return filtered
```

---

## Agent Swarm Architecture

### How Agents Create Plays

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AGENT TRADING SWARM                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     ANALYST AGENTS (Parallel)                       │    │
│  ├─────────────────────────────────────────────────────────────────────┤    │
│  │                                                                     │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────┐  │    │
│  │  │ Technical   │  │ Structure   │  │ Sentiment   │  │ Forecast  │  │    │
│  │  │ Analyst     │  │ Analyst     │  │ Analyst     │  │ Agent     │  │    │
│  │  ├─────────────┤  ├─────────────┤  ├─────────────┤  ├───────────┤  │    │
│  │  │ Indicators  │  │ Swing/Zones │  │ News/Social │  │ ML Model  │  │    │
│  │  │ Patterns    │  │ Order Flow  │  │ Fear/Greed  │  │ Predict   │  │    │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └─────┬─────┘  │    │
│  │         │                │                │               │        │    │
│  │         └────────────────┴────────────────┴───────────────┘        │    │
│  │                                   │                                │    │
│  └───────────────────────────────────┼────────────────────────────────┘    │
│                                      ▼                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     DEBATE AGENTS (Sequential)                      │    │
│  ├─────────────────────────────────────────────────────────────────────┤    │
│  │                                                                     │    │
│  │  ┌───────────────────┐           ┌───────────────────┐             │    │
│  │  │   BULL AGENT      │ ◄─────►   │   BEAR AGENT      │             │    │
│  │  │   (Argues long)   │  Debate   │   (Argues short)  │             │    │
│  │  └─────────┬─────────┘           └─────────┬─────────┘             │    │
│  │            │                               │                        │    │
│  │            └───────────────┬───────────────┘                        │    │
│  │                            ▼                                        │    │
│  │            ┌───────────────────────────────┐                        │    │
│  │            │       RISK AGENT              │                        │    │
│  │            │       (Veto power)            │                        │    │
│  │            └───────────────┬───────────────┘                        │    │
│  │                            │                                        │    │
│  └────────────────────────────┼────────────────────────────────────────┘    │
│                               ▼                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     SYNTHESIS AGENT                                 │    │
│  ├─────────────────────────────────────────────────────────────────────┤    │
│  │                                                                     │    │
│  │   Takes: Analyst reports + Debate outcome + Risk constraints        │    │
│  │                                                                     │    │
│  │   Produces: Play YAML                                           │    │
│  │                                                                     │    │
│  │   ┌─────────────────────────────────────────────────────────────┐   │    │
│  │   │ name: "swarm_btc_long_v1"                                   │   │    │
│  │   │ features:                                                   │   │    │
│  │   │   - type: ema                                               │   │    │
│  │   │     id: ema_fast                                            │   │    │
│  │   │     params: { length: 21 }                                  │   │    │
│  │   │   - type: swing                                             │   │    │
│  │   │     id: swing                                               │   │    │
│  │   │     params: { left: 5, right: 5 }                           │   │    │
│  │   │ blocks:                                                     │   │    │
│  │   │   - id: entry                                               │   │    │
│  │   │     cases:                                                  │   │    │
│  │   │       - when: { all: [...] }                                │   │    │
│  │   │         emit: [{ action: entry_long }]                      │   │    │
│  │   └─────────────────────────────────────────────────────────────┘   │    │
│  │                                                                     │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                               │                                             │
│                               ▼                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     VALIDATION (Backtest)                           │    │
│  │                                                                     │    │
│  │   Play → Engine → Metrics → Accept/Reject/Refine               │    │
│  │                                                                     │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Agent-Play Protocol

```python
# ============================================================
# AGENT TOOLS: How agents interact with the trading system
# ============================================================

class TradingAgentTools:
    """
    Tools available to agents for trading system interaction.

    These are the ONLY ways agents can affect trading.
    All agent actions go through Plays.
    """

    # ==================== READ TOOLS ====================

    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        """Get current market state (prices, indicators, structures)."""
        ...

    def get_available_features(self) -> list[FeatureSpec]:
        """List all available indicators and structures."""
        ...

    def get_play_template(self) -> str:
        """Get blank Play YAML template."""
        ...

    def validate_play(self, yaml: str) -> ValidationResult:
        """Validate Play syntax and semantics."""
        ...

    # ==================== BACKTEST TOOLS ====================

    def backtest_play(
        self,
        yaml: str,
        window: str = "hygiene",
    ) -> BacktestResult:
        """Run backtest on Play, return metrics."""
        ...

    def compare_plays(
        self,
        cards: list[str],
    ) -> ComparisonReport:
        """Compare multiple Plays on same data."""
        ...

    # ==================== WRITE TOOLS ====================

    def submit_play(
        self,
        yaml: str,
        mode: Literal["demo", "live"],
    ) -> SubmissionResult:
        """Submit validated Play for execution."""
        ...

    def update_play(
        self,
        card_id: str,
        yaml: str,
    ) -> UpdateResult:
        """Update existing Play (hot-swap in demo/live)."""
        ...

    def deactivate_play(
        self,
        card_id: str,
    ) -> DeactivationResult:
        """Deactivate Play, close positions."""
        ...
```

---

## Evolution/ML Integration

### Genetic Algorithm on Plays

```python
class PlayEvolution:
    """
    Evolve Plays via genetic algorithm.

    Genes: Play parameters (indicator lengths, thresholds, etc.)
    Fitness: Backtest metrics (Sharpe, win rate, etc.)
    """

    def __init__(
        self,
        population_size: int = 50,
        generations: int = 100,
        mutation_rate: float = 0.1,
        crossover_rate: float = 0.7,
    ):
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate

    def evolve(self, base_card: Play) -> Play:
        """
        Evolve Play to optimize fitness.

        1. Generate initial population (random mutations of base)
        2. Evaluate fitness (backtest each)
        3. Select parents (tournament selection)
        4. Crossover (combine parent genes)
        5. Mutate (random parameter changes)
        6. Repeat until convergence
        """
        population = self._init_population(base_card)

        for gen in range(self.generations):
            # Evaluate fitness (parallel backtests)
            fitness = self._evaluate_population(population)

            # Select best
            parents = self._select_parents(population, fitness)

            # Create next generation
            population = self._breed(parents)

            # Log progress
            best_fitness = max(fitness)
            print(f"Gen {gen}: Best fitness = {best_fitness:.3f}")

        # Return best individual
        return population[np.argmax(fitness)]

    def _mutate(self, card: Play) -> Play:
        """
        Mutate Play parameters.

        Mutable genes:
        - Indicator lengths (EMA, ATR, etc.)
        - Structure params (swing left/right)
        - Threshold values
        - Execution params (size_pct, etc.)
        """
        mutated = card.copy()

        for feature in mutated.features:
            if random.random() < self.mutation_rate:
                # Mutate a random parameter
                param = random.choice(list(feature.params.keys()))
                current = feature.params[param]

                if isinstance(current, int):
                    # Integer mutation: ±1 to ±20%
                    delta = random.randint(-max(1, current // 5), max(1, current // 5))
                    feature.params[param] = max(1, current + delta)
                elif isinstance(current, float):
                    # Float mutation: ±10%
                    feature.params[param] = current * random.uniform(0.9, 1.1)

        return mutated
```

### RL Agent Play Generation

```python
class RLPlayAgent:
    """
    RL agent that learns to generate profitable Plays.

    State: Market features + current position
    Action: Play parameter adjustments
    Reward: Backtest Sharpe ratio
    """

    def __init__(self, base_card: Play):
        self.base_card = base_card
        self.action_space = self._build_action_space(base_card)
        self.policy = self._init_policy()

    def _build_action_space(self, card: Play) -> ActionSpace:
        """
        Action space is the set of adjustable parameters.

        Each parameter becomes a continuous action dimension.
        """
        actions = []
        for feature in card.features:
            for param, value in feature.params.items():
                if isinstance(value, (int, float)):
                    actions.append(ParameterAction(
                        feature_id=feature.id,
                        param=param,
                        min_val=value * 0.5,
                        max_val=value * 2.0,
                    ))
        return ActionSpace(actions)

    def generate_card(self, market_state: MarketSnapshot) -> Play:
        """
        Generate Play based on current market state.

        The policy outputs parameter adjustments conditioned on market.
        """
        # Encode market state
        state_encoding = self._encode_state(market_state)

        # Get action from policy
        action = self.policy(state_encoding)

        # Apply action to base card
        card = self._apply_action(self.base_card, action)

        return card
```

---

## Tool-Based Architecture

### Registry of Trading Tools

```python
# ============================================================
# TOOL REGISTRY: All trading operations are tools
# ============================================================

TRADING_TOOLS = {
    # ==================== DATA TOOLS ====================
    "get_snapshot": GetSnapshotTool,
    "get_history": GetHistoryTool,
    "get_features": GetFeaturesTool,
    "get_structures": GetStructuresTool,

    # ==================== PLAY TOOLS ====================
    "validate_card": ValidateCardTool,
    "normalize_card": NormalizeCardTool,
    "backtest_card": BacktestCardTool,
    "compare_cards": CompareCardsTool,

    # ==================== EXECUTION TOOLS ====================
    "submit_card": SubmitCardTool,
    "update_card": UpdateCardTool,
    "deactivate_card": DeactivateCardTool,

    # ==================== POSITION TOOLS ====================
    "get_positions": GetPositionsTool,
    "get_orders": GetOrdersTool,
    "cancel_order": CancelOrderTool,
    "panic_close": PanicCloseTool,

    # ==================== PLAYBOOK TOOLS ====================
    "load_playbook": LoadPlaybookTool,
    "execute_playbook": ExecutePlaybookTool,
    "get_regime": GetRegimeTool,

    # ==================== AGENT TOOLS ====================
    "get_analyst_report": GetAnalystReportTool,
    "get_forecast": GetForecastTool,
    "get_consensus": GetConsensusTool,
}
```

### Tool Protocol

```python
class TradingTool(Protocol):
    """
    Universal tool protocol.

    All trading operations implement this interface.
    Agents interact ONLY through tools.
    """

    name: str
    description: str
    parameters: dict[str, ParameterSpec]

    def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with given parameters."""
        ...

    def validate(self, **kwargs) -> ValidationResult:
        """Validate parameters before execution."""
        ...

    def to_openai_schema(self) -> dict:
        """Convert to OpenAI function calling schema."""
        ...

    def to_anthropic_schema(self) -> dict:
        """Convert to Anthropic tool use schema."""
        ...
```

---

## Summary: The Core Trading Language

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  HUMAN           AGENT SWARM         EVOLUTION/ML                           │
│    │                  │                   │                                 │
│    │                  │                   │                                 │
│    ▼                  ▼                   ▼                                 │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                        PLAY YAML                                  │  │
│  │                   (The Core Trading Language)                         │  │
│  │                                                                       │  │
│  │   Same format, same semantics, same validation                        │  │
│  │   Who wrote it doesn't matter - only that it's valid                  │  │
│  │                                                                       │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                │                                            │
│                                ▼                                            │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                        TOOL LAYER                                     │  │
│  │                                                                       │  │
│  │   validate_card() → normalize_card() → backtest_card() → submit_card()│  │
│  │                                                                       │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                │                                            │
│                                ▼                                            │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                     UNIFIED ENGINE                                    │  │
│  │                                                                       │  │
│  │   Simulator ─────► Demo ─────► Live                                   │  │
│  │   (Same code path, different execution backend)                       │  │
│  │                                                                       │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                │                                            │
│                                ▼                                            │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                        STATE BUFFER                                   │  │
│  │                                                                       │  │
│  │   Universal state for all features, dynamic depth, O(1) access        │  │
│  │   Agents can query: "What was EMA 5 bars ago?"                        │  │
│  │                                                                       │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**This is your true agent trading swarm.**

- **Play is the contract** - human, agent, or ML all produce the same format
- **Tools are the interface** - all operations go through registered tools
- **Engine is the runtime** - same code for sim/demo/live
- **State buffer is universal** - any feature, any depth, O(1) access

The punch card analogy is perfect. **Plays are the new punch cards.**
