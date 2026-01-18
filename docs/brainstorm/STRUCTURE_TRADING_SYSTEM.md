# Brainstorm: Structure-Based Trading System Architecture

> **Status**: Active brainstorm document
> **Last Updated**: 2026-01-17
> **Purpose**: Capture evolving ideas for ICT/SMC market structure trading

---

## Summary

Comprehensive redesign of TRADE's structure system to enable proper market structure trading (ICT/SMC concepts) that works for both backtesting and live trading, with support for multi-strategy deployment.

**Key Goals:**
1. Extended pivot history (track last N pivots, not just most recent)
2. HH/HL/LH/LL classification for market structure
3. Proper BOS/ChoCH detection with context awareness
4. Unified TradingRun abstraction for backtest/demo/live
5. End-to-end flow from Play concept to live deployment

---

## Problem Statement

### Current "Goldfish Memory" Issue

```
Current swing detector only tracks:
  - high_level, high_idx (MOST RECENT swing high)
  - low_level, low_idx (MOST RECENT swing low)

LOST FOREVER:
  - Previous pivots
  - Pivot sequence (HH/HL/LH/LL pattern)
  - Structure context for BOS/ChoCH
```

### ICT/SMC Concepts Needed

| Concept | Description | Current Support |
|---------|-------------|-----------------|
| Higher High (HH) | New high > previous high | NO - no history |
| Higher Low (HL) | New low > previous low | NO - no history |
| Lower High (LH) | New high < previous high | NO - no history |
| Lower Low (LL) | New low < previous low | NO - no history |
| Break of Structure (BOS) | Price closes beyond key level | PARTIAL |
| Change of Character (ChoCH) | Price breaks opposite level | PARTIAL |

**Sources:**
- [ICT Market Structure Shift](https://innercircletrader.net/tutorials/ict-market-structure-shift/)
- [Higher Highs and Higher Lows Trading](https://tradingfinder.com/education/forex/ict-higher-highs-higher-lows/)
- [smart-money-concepts Python Package](https://github.com/joshyattridge/smart-money-concepts)

---

## Architecture Design

### 1. Extended Pivot History Buffer

**New Data Structure: PivotRingBuffer**

```python
# File: src/structures/pivot_buffer.py (NEW)

@dataclass(frozen=True, slots=True)
class Pivot:
    idx: int              # Bar index
    level: float          # Price level
    pivot_type: str       # "high" or "low"
    atr_at_pivot: float   # For significance filtering
    significance: float   # ATR multiple from previous
    is_major: bool        # >= threshold
    timestamp: datetime

class PivotRingBuffer:
    """Track last N pivots (not bars). Default N=20."""

    push(pivot) -> None           # O(1)
    get_last_n(n, type) -> list   # O(n)
    get_last_high() -> Pivot      # O(N) worst
    get_last_low() -> Pivot       # O(N) worst
```

**Integration with Swing Detector:**

```python
# File: src/structures/detectors/swing.py (MODIFY)

# New instance variables:
_pivot_history: PivotRingBuffer  # Size 20
_last_high_type: str             # "HH" or "LH"
_last_low_type: str              # "HL" or "LL"

# New output keys:
last_high_type      # "HH" or "LH"
last_low_type       # "HL" or "LL"
pivot_history_count # Number in buffer
hh_count_last_10    # Trend strength
hl_count_last_10    # Trend strength
```

### 2. Market Structure State Machine

```
States:
  UNDEFINED (0)  - Not enough pivots
  BULLISH (1)    - Making HH + HL
  BEARISH (-1)   - Making LH + LL
  RANGING (2)    - Mixed signals

Transitions:
                    ┌─────────────┐
                    │  UNDEFINED  │
                    └──────┬──────┘
                           │
              BOS Up       │       BOS Down
              ┌────────────┴────────────┐
              ▼                         ▼
       ┌──────────┐              ┌──────────┐
       │ BULLISH  │◄────CHoCH────│ BEARISH  │
       └────┬─────┘              └────┬─────┘
            │ LH forms                │ HL forms
            ▼                         ▼
       ┌──────────┐              ┌──────────┐
       │ RANGING  │◄────────────►│ RANGING  │
       └──────────┘              └──────────┘
```

**Enhanced Market Structure Detector:**

```python
# File: src/structures/detectors/market_structure.py (MODIFY)

# Key changes:
#   1. Use swing._pivot_history for context
#   2. Proper CHoCH requires opposite pivot first
#   3. ATR-based filtering of stale break levels
#   4. Trend strength from consecutive HH/HL or LH/LL
```

### 3. Context Reset Logic

```python
# File: src/engine/context_reset.py (NEW)

class ContextResetConfig:
    max_pivot_age_bars: int = 100    # Time-based filter
    max_atr_distance: float = 10.0   # Price-based filter
    reset_on_choch: bool = True      # Structure-based
    reset_on_major_gap: bool = True  # Gap > 3*ATR

class ContextResetManager:
    should_invalidate_pivot(pivot, current_idx, atr, price) -> bool
    check_gap_reset(prev_close, current_open, atr) -> bool
```

### 4. Unified TradingRun Abstraction

```
                    ┌─────────────────────────────────┐
                    │          TradingRun             │
                    │  (mode-agnostic orchestrator)   │
                    └───────────────┬─────────────────┘
                                    │
           ┌────────────────────────┼────────────────────────┐
           │                        │                        │
           ▼                        ▼                        ▼
    ┌──────────────┐        ┌──────────────┐        ┌──────────────┐
    │   Backtest   │        │    Demo      │        │    Live      │
    │  FeedStore   │        │  WebSocket   │        │  WebSocket   │
    │  SimExchange │        │  DemoAPI     │        │  LiveAPI     │
    └──────────────┘        └──────────────┘        └──────────────┘

Key features:
  - Same engine code for all modes
  - Session management (start/pause/resume/stop)
  - State persistence for crash recovery
  - Checkpoint interval for incremental state
```

### 5. Multi-Strategy Deployment

```python
# File: src/engine/portfolio.py (NEW)

class PortfolioManager:
    """Manage multiple TradingRuns across strategies/symbols."""

    add_strategy(play, allocation_pct, mode) -> run_id
    get_portfolio_exposure() -> dict
    rebalance_allocations() -> None

    # Each Play gets isolated TradingRun
    # Risk allocation shared across portfolio
```

### 6. End-to-End Promotion Flow

```
Play YAML → Validation → Backtest → Demo → Live
     │           │            │         │       │
     │           │            │         │       └── Real money
     │           │            │         └── Paper trading (7+ days)
     │           │            └── Historical testing (min Sharpe, trades)
     │           └── Schema + smoke tests
     └── Strategy definition

Promotion Gates:
  Backtest → Demo:  Sharpe >= 1.0, Trades >= 50, MaxDD <= 20%
  Demo → Live:      7 days, 10+ trades, no critical errors
```

---

## Files Summary

### Files to Create (NEW)

| File | Purpose | Priority | Complexity |
|------|---------|----------|------------|
| `src/structures/pivot_buffer.py` | Pivot + PivotRingBuffer | P0 | Medium |
| `src/engine/trading_run.py` | TradingRun + TradingSession | P1 | High |
| `src/engine/context_reset.py` | ContextResetConfig + Manager | P1 | Medium |
| `src/engine/portfolio.py` | PortfolioManager | P2 | Medium |
| `src/cli/commands/promote.py` | Promotion workflow CLI | P3 | Low |

### Files to Modify

| File | Changes | Priority |
|------|---------|----------|
| `src/structures/detectors/swing.py` | Add pivot history, HH/HL/LH/LL | P0 |
| `src/structures/detectors/market_structure.py` | Integrate pivot history | P0 |
| `src/structures/primitives.py` | Import pivot_buffer | P0 |
| `src/structures/state.py` | Pivot history serialization | P1 |
| `src/engine/play_engine.py` | Integrate TradingRun | P1 |
| `src/backtest/play/play.py` | Parse new swing params | P1 |

---

## Implementation Phases

### Phase 1: Extended Pivot History (P0)
**Goal**: Enable HH/HL/LH/LL classification

Tasks:
1. Create `src/structures/pivot_buffer.py` with Pivot + PivotRingBuffer
2. Modify `swing.py` to maintain pivot history
3. Add classification logic (_classify_pivot method)
4. Add new output keys (last_high_type, last_low_type, etc.)
5. Update structure registry for new output types
6. Create validation Play to test HH/HL/LH/LL detection

### Phase 2: Enhanced Market Structure (P0)
**Goal**: Proper BOS/ChoCH with context awareness

Tasks:
1. Create `src/engine/context_reset.py`
2. Enhance `market_structure.py` to use swing._pivot_history
3. Implement state machine transitions
4. Add trend strength outputs (consecutive_hh, etc.)
5. Create validation Play for BOS/ChoCH detection

### Phase 3: Unified Run Abstraction (P1)
**Goal**: Single interface for backtest/demo/live

Tasks:
1. Create `src/engine/trading_run.py`
2. Integrate TradingSession with PlayEngine
3. Add state persistence (checkpoint/restore)
4. Update CLI commands to use TradingRun
5. End-to-end test: same Play in all modes

### Phase 4: Multi-Strategy Deployment (P2)
**Goal**: Run multiple Plays concurrently

Tasks:
1. Create `src/engine/portfolio.py`
2. Add risk allocation logic
3. Implement process isolation for parallel runs
4. Create CLI for portfolio management
5. Add monitoring hooks

---

## Backward Compatibility

### Play YAML (Additive Only)

```yaml
# EXISTING (still works, no changes required)
structures:
  exec:
    - type: swing
      key: swing
      params:
        left: 5
        right: 5

# NEW OPTIONAL PARAMS
structures:
  exec:
    - type: swing
      key: swing
      params:
        left: 5
        right: 5
        pivot_history_size: 20   # NEW, default 20
        classify_pivots: true    # NEW, default true
```

### API Compatibility (Additive Only)

```python
# EXISTING (unchanged)
swing.high_level
swing.low_level
swing.pair_direction

# NEW OUTPUTS (opt-in access)
swing.last_high_type     # "HH" or "LH"
swing.last_low_type      # "HL" or "LL"
swing.pivot_history_count
```

---

## Verification Plan

### Phase 1 Verification
```bash
# Create test Play with swing history
python trade_cli.py backtest play-normalize --play V_SWING_HISTORY_001

# Run backtest and check HH/HL/LH/LL outputs
python trade_cli.py backtest run --play V_SWING_HISTORY_001 --smoke

# Verify outputs in artifacts
cat backtests/_validation/V_SWING_HISTORY_001/*/result.json | jq '.structure_outputs'
```

### Phase 2 Verification
```bash
# Test BOS/ChoCH detection
python trade_cli.py backtest run --play V_MARKET_STRUCTURE_001 --smoke

# Check state transitions in event log
python trade_cli.py backtest inspect --play V_MARKET_STRUCTURE_001 --events
```

### Phase 3 Verification
```bash
# Test unified run abstraction
python trade_cli.py trading-run start --play T_001_minimal --mode demo
python trade_cli.py trading-run status --run-id <id>
python trade_cli.py trading-run stop --run-id <id>
```

### Phase 4 Verification
```bash
# Test portfolio management
python trade_cli.py portfolio add --play T_001 --allocation 50
python trade_cli.py portfolio add --play T_002 --allocation 50
python trade_cli.py portfolio start --mode demo
python trade_cli.py portfolio status
```

---

## Architecture Diagram

```
┌────────────────────────────────────────────────────────────────────────────┐
│                              TRADE ARCHITECTURE                            │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌─────────────┐     ┌──────────────────────────────────────────────────┐  │
│  │  Play YAML  │────▶│              FeatureRegistry                     │  │
│  │ (Strategy)  │     │  Indicators + Structures (with pivot history)   │  │
│  └─────────────┘     └───────────────────────┬──────────────────────────┘  │
│                                              │                             │
│                                              ▼                             │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │                        TradingRun                                     │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                │ │
│  │  │   Session    │  │   Session    │  │   Session    │                │ │
│  │  │  (backtest)  │  │   (demo)     │  │   (live)     │                │ │
│  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘                │ │
│  │         │                 │                 │                         │ │
│  │         └─────────────────┴─────────────────┘                         │ │
│  │                           │                                           │ │
│  │                           ▼                                           │ │
│  │  ┌────────────────────────────────────────────────────────────────┐  │ │
│  │  │                     PlayEngine                                 │  │ │
│  │  │  (mode-agnostic signal generation + execution)                │  │ │
│  │  └──────────────────────────┬─────────────────────────────────────┘  │ │
│  │                             │                                        │ │
│  └─────────────────────────────┼────────────────────────────────────────┘ │
│                                │                                          │
│         ┌──────────────────────┼──────────────────────┐                   │
│         │                      │                      │                   │
│         ▼                      ▼                      ▼                   │
│  ┌─────────────┐       ┌─────────────┐       ┌─────────────┐             │
│  │  FeedStore  │       │  WebSocket  │       │  WebSocket  │             │
│  │ (backtest)  │       │   (demo)    │       │   (live)    │             │
│  └─────────────┘       └─────────────┘       └─────────────┘             │
│                                                                           │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │                    Structure System                                │   │
│  │  ┌───────────────────────────────────────────────────────────────┐│   │
│  │  │ IncrementalSwingDetector (with PivotRingBuffer)               ││   │
│  │  │   - Tracks last 20 pivots                                     ││   │
│  │  │   - Classifies HH/HL/LH/LL                                    ││   │
│  │  │   - Provides history for downstream structures                ││   │
│  │  └─────────────────────────────────┬─────────────────────────────┘│   │
│  │                                    │                              │   │
│  │  ┌─────────────────────────────────▼─────────────────────────────┐│   │
│  │  │ EnhancedMarketStructure                                       ││   │
│  │  │   - Uses pivot history for context                            ││   │
│  │  │   - Proper BOS/ChoCH with state machine                       ││   │
│  │  │   - Trend strength from consecutive HH/HL                     ││   │
│  │  └───────────────────────────────────────────────────────────────┘│   │
│  │                                                                    │   │
│  │  ┌───────────────────┐  ┌───────────────┐  ┌────────────────────┐ │   │
│  │  │    Fibonacci      │  │   DerivedZone  │  │   RollingWindow   │ │   │
│  │  │ (uses pair anchor)│  │ (from swings) │  │    (min/max)      │ │   │
│  │  └───────────────────┘  └───────────────┘  └────────────────────┘ │   │
│  └───────────────────────────────────────────────────────────────────┘   │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## Conversation Log

### 2026-01-17: Initial Brainstorm

**User Observation**: "The current system feels like it was built for simple indicator-based trading, not structure-based trading."

**Key Insights**:
- Current swing detector has "goldfish memory" - only tracks most recent pivot
- No HH/HL/LH/LL classification possible without pivot history
- BOS/ChoCH detection is partial without proper context
- Need unified abstraction for backtest/demo/live trading

**Proposed Solution**:
- PivotRingBuffer to track last 20 pivots
- Classification on each new pivot (compare to previous same-type)
- State machine for market structure (UNDEFINED → BULLISH/BEARISH ↔ RANGING)
- TradingRun abstraction for mode-agnostic engine execution

---

## Open Questions

1. **Pivot significance threshold**: How many ATR multiples for "major" vs "minor" pivots?
2. **Context reset triggers**: What events should clear pivot history?
3. **Multi-timeframe pivot hierarchy**: How do higher timeframe pivots relate to lower timeframe?
4. **Performance**: Is O(N) pivot search acceptable, or need O(1) with separate high/low buffers?

---

## Next Steps

When ready to implement:
1. Start with Phase 1 (pivot history buffer)
2. Create test Plays to validate HH/HL/LH/LL detection
3. Proceed to Phase 2 (market structure enhancement)
4. Then Phase 3 (unified run abstraction)
5. Finally Phase 4 (multi-strategy deployment)

Each phase is independently valuable and can be deployed incrementally.
