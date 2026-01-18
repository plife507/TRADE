# Brainstorm: Trading DSL & Block Architecture

> **Status**: Active brainstorm
> **Last Updated**: 2026-01-17
> **Purpose**: Design a trading DSL that bridges agent intent and Python execution

---

## Vision

Build a declarative trading language where:
- **Logic** (primitives) -> **Blocks** (composed logic) -> **Plays** (strategies)
- Extensible to new signal sources (indicators, structures, sentiment, confluence)
- Three logic domains: Temporal, Quantitative, Descriptive

---

## Crypto Trader Primitives

### Temporal - What Actually Matters in Crypto
```yaml
- cme_open                # CME futures open (real gaps)
- weekly_open             # Sunday open as key level
- funding_interval        # 8h funding timestamp
- time_since_ath          # Days from all-time high
- time_since_local_high   # Bars since swing high
- duration_in_range       # How long in current range
```

Sessions (Asian/London/NY) are forex concepts with weak evidence in crypto. Deprioritized.

### Quantitative - What Moves Price
```yaml
- liquidation_levels      # Where stops cluster
- funding_rate            # Crowded trade signal
- open_interest_delta     # New money or closing
- cvd                     # Cumulative volume delta
- exchange_delta          # Coins moving on/off exchange
```

### Crypto-Native Signals (Priority)

These are unique to crypto and should be first-class primitives:

**Perpetual Futures:**
```yaml
- funding_rate            # Positive = longs pay shorts
- funding_predicted       # Next funding estimate
- basis                   # Spot vs perp spread
- open_interest           # Total positions
- oi_delta                # Change in OI
```

**Liquidation & Leverage:**
```yaml
- liquidation_levels      # Where cascades happen
- estimated_leverage      # OI / market cap proxy
- long_short_ratio        # Exchange reported
```

**On-Chain (Future):**
```yaml
- exchange_netflow        # Coins in/out of exchanges
- whale_transactions      # Large transfers
- active_addresses        # Network activity
- stablecoin_supply       # Dry powder
```

**Order Flow:**
```yaml
- cvd                     # Cumulative volume delta
- aggressor_side          # Who's hitting market orders
- large_trade_flow        # Block trades direction
```

### Descriptive - Market Regime
```yaml
- regime: trending | ranging | choppy | squeeze
- volatility_state: compressed | expanding
- high_tf_bias: bullish | bearish | neutral
- liquidity: above_price | below_price | both
```

---

## Block Types (Trader Mental Model)

### 1. Filter Blocks (When NOT to Trade)
```yaml
blocks:
  no_chop:
    type: filter
    logic:
      all:
        - [adx, ">", 20]

  no_crowded_longs:
    type: filter
    logic:
      all:
        - [funding_rate, "<", 0.05]
```

### 2. Entry Blocks (Setups)
```yaml
blocks:
  liquidity_grab:
    type: entry
    logic:
      sequence:
        - [low, "<", prev_swing_low]
        - [close, ">", prev_swing_low]
        - within: 3 bars
```

### 3. Exit Blocks (Take Profit Logic)
```yaml
blocks:
  scale_out:
    type: exit
    logic:
      steps:
        - at: 1R, close: 50%
        - at: 2R, close: 30%
        - at: 3R, close: remaining
```

### 4. Invalidation Blocks (Thesis Wrong)
```yaml
blocks:
  structure_break:
    type: invalidation
    logic:
      any:
        - [close, "<", entry_swing_low]
        - [structure, "=", choch_bearish]
```

---

## Architecture Options

### Option A: Flat Blocks
```
Logic -> Blocks -> Plays
```
Simple. Each block is independent. Plays compose them.

### Option B: Typed Blocks (PREFERRED)
```
Logic -> Typed Blocks (filter|entry|exit|invalidation) -> Plays
```
Blocks have roles. Engine knows what each type does.

### Option C: Layered Blocks
```
Logic -> Micro-blocks -> Macro-blocks -> Plays
```
Micro: single condition. Macro: composed. More flexible, more complex.

---

## Current Gaps

| Gap | Why It Matters |
|-----|----------------|
| Crypto-native data | Funding, OI, liquidations - the actual edge |
| Invalidation logic | "Setup failed" != "hit risk limit" |
| Regime filter | Best setup in chop = still a loss |
| Sequence operators | "A then B within 3 bars" - how setups work |
| Confluence scoring | 3/5 signals = maybe, 5/5 = send it |
| Liquidity concepts | Stops, sweeps, grabs - the real game |

---

## Conversation Log

### 2026-01-17: Initial DSL Discussion
- User vision: trading programming language bridging agent and Python
- Logic -> Blocks -> Plays composition flow
- Three logic domains: temporal, quantitative, descriptive
- Decided to focus on Option B (Typed Blocks)

### 2026-01-17: Crypto-Native Focus
- Removed forex session concepts - weak evidence in crypto
- CME open/weekly open retained (real events)
- Prioritized: funding, OI, liquidations, on-chain
- Sessions deprioritized until proven with data

---

## Open Questions

1. How do typed blocks interact? Can entry block reference filter block?
2. Invalidation vs stop loss - how to express both?
3. Sequence operator syntax - what's clean?
4. Block versioning - how to evolve without breaking Plays?
