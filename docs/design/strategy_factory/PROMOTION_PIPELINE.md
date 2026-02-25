# Promotion Pipeline: From Backtest to Live

## Overview

Strategies flow through increasingly rigorous validation stages.
Each stage has clear entry/exit criteria. Failures demote back.

```
BACKTEST ──► LIVE SIM ──► DEMO ──► LIVE
 (minutes)   (days)       (days)   (ongoing)
  filter      validate     confirm   trade
  1000→50     50→10        10→3      3 active
```

## Stage Definitions

### Stage 1: Backtest (Synthetic)

**Purpose**: Fast elimination of obviously bad strategies.

**Environment**: Synthetic data, SimulatedExchange, ProcessPoolExecutor.

**Entry**: Any generated Play YAML.

**Duration**: ~3s per play.

**Pass criteria**:
- Total trades >= 10
- Sharpe ratio > 0.5
- Max drawdown < 30%
- No runtime errors

**Typical survival rate**: ~30% (1000 → 300)

---

### Stage 2: Backtest (Real Data)

**Purpose**: Verify strategy works on actual market data, not just synthetic.

**Environment**: DuckDB historical data, SimulatedExchange.

**Entry**: Passed Stage 1.

**Duration**: ~10s per play.

**Pass criteria**:
- Sharpe ratio > 1.0
- Max drawdown < 20%
- Profit factor > 1.3
- Win rate > 35%
- Consistent across multiple date windows (walk-forward)

**Typical survival rate**: ~25% (300 → 75)

---

### Stage 3: Walk-Forward Validation

**Purpose**: Detect overfitting by testing on out-of-sample periods.

**Method**: Split historical data into train/test windows. Backtest on
train, validate on test. Repeat with rolling windows.

```
|---train---|--test--|
        |---train---|--test--|
                |---train---|--test--|
```

**Entry**: Passed Stage 2.

**Pass criteria**:
- Test performance within 50% of train performance
- No window with negative Sharpe
- Consistent win rate across windows (stdev < 15%)

**Typical survival rate**: ~40% (75 → 30)

---

### Stage 4: Live Sim (Forward Test)

**Purpose**: Prove strategy works on unseen real-time data.
This is the critical overfitting filter.

**Environment**: WebSocket real-time data, SimulatedExchange (local).

**Entry**: Passed Stage 3.

**Duration**: Minimum 7 days, 10+ trades.

**Monitoring**:
- Equity curve updated in real-time
- Rolling Sharpe, drawdown, win rate
- Comparison to backtest expectations

**Pass criteria**:
- Sharpe > 1.0 (over full observation period)
- Max drawdown < 15%
- Win rate within 15% of backtest win rate
- Profit factor > 1.5
- No prolonged losing streaks (> 5 consecutive losses)

**Demotion criteria** (auto-remove from live sim):
- Drawdown exceeds 25%
- 7+ consecutive losses
- Sharpe drops below -0.5 (sustained losing)

**Typical survival rate**: ~30% (30 → 10)

---

### Stage 5: Demo (Paper Trading)

**Purpose**: Validate execution quality — fills, slippage, TP/SL behavior
match live sim expectations.

**Environment**: Bybit demo API (testnet), real order matching engine.

**Entry**: Passed Stage 4. Manual approval required.

**Duration**: Minimum 14 days, 20+ trades.

**Key differences from Live Sim**:
- Real order matching (not simulated fills)
- Real slippage and spread
- Real WebSocket fill confirmations
- Exchange-native TP/SL orders

**Pass criteria**:
- Performance within 20% of live sim results
- No fill quality issues (excessive slippage, missed fills)
- No technical errors (disconnects, missed signals)
- TP/SL execution matches expectations

**Demotion criteria**:
- Performance deviates > 30% from live sim
- Systematic fill issues
- Critical technical errors

**Typical survival rate**: ~50% (10 → 5)

---

### Stage 6: Live (Real Money)

**Purpose**: Generate actual returns.

**Environment**: Bybit production API, sub-account isolation.

**Entry**: Passed Stage 5. Explicit user confirmation required.

**Capital allocation**:
- Start with minimum viable capital ($100-500)
- Scale up based on continued performance
- Auto-reduce on drawdown breach

**Monitoring**:
- Real-time PnL tracking
- Position sync verification (every 5 min)
- Rate limit monitoring (shared across sub-accounts)
- Circuit breaker on max drawdown

**Demotion criteria**:
- Drawdown exceeds configured max (e.g., 10%)
- Sustained underperformance vs expectations
- Technical failures (missed reconciliation, orphan positions)

---

## Scoring Function

### Composite Score

Used at every stage to rank and filter plays:

```python
@dataclass
class PlayScore:
    play_id: str
    stage: str
    sharpe_ratio: float
    max_drawdown_pct: float
    win_rate: float
    profit_factor: float
    total_trades: int
    avg_trade_duration: float  # hours
    consistency: float         # stdev of per-window Sharpe

    @property
    def composite(self) -> float:
        """Weighted composite score. Higher = better."""
        if self.total_trades < 10:
            return -999.0

        score = (
            self.sharpe_ratio * 0.30
            + (1 - self.max_drawdown_pct / 100) * 0.25
            + self.win_rate * 0.15
            + min(self.profit_factor / 3.0, 1.0) * 0.15
            + min(self.total_trades / 50, 1.0) * 0.10
            + (1 - min(self.consistency, 1.0)) * 0.05
        )
        return round(score, 4)
```

### Stage-Specific Thresholds

| Metric | Backtest Synth | Backtest Real | Live Sim | Demo | Live |
|--------|---------------|---------------|----------|------|------|
| Min Sharpe | 0.5 | 1.0 | 1.0 | 0.8 | 0.5 |
| Max DD% | 30 | 20 | 15 | 15 | 10 |
| Min Win% | 30 | 35 | 40 | 40 | 35 |
| Min Trades | 10 | 10 | 10 | 20 | 20 |
| Min PF | 1.0 | 1.3 | 1.5 | 1.3 | 1.2 |

---

## Promotion & Demotion Flow

### Auto-Promotion

Promotion happens when ALL criteria for the next stage are met:

```python
class PromotionEngine:
    """Evaluate plays for promotion/demotion."""

    def evaluate(self, play_id: str, stage: str, stats: PlayStats) -> Action:
        criteria = self._get_criteria(stage)

        if self._meets_promotion_criteria(stats, criteria.promote):
            return Action.PROMOTE

        if self._meets_demotion_criteria(stats, criteria.demote):
            return Action.DEMOTE

        return Action.HOLD  # Keep observing
```

### Auto-Demotion

Demotion is immediate when any hard limit is breached:

```python
DEMOTION_TRIGGERS = {
    "live_sim": {
        "max_drawdown_pct": 25.0,
        "max_consecutive_losses": 7,
        "min_sharpe": -0.5,        # Sustained losing
    },
    "demo": {
        "max_drawdown_pct": 20.0,
        "performance_deviation": 0.30,  # 30% worse than live sim
    },
    "live": {
        "max_drawdown_pct": 10.0,   # Tighter for real money
        "max_consecutive_losses": 5,
    },
}
```

### Demotion Path

```
Live → Demo (reduce capital, keep observing)
Demo → Live Sim (remove from exchange, keep simulating)
Live Sim → Archive (stop simulation, log results)
```

A demoted play can be re-promoted if it recovers. The system tracks
the full history of promotions/demotions for each play.

---

## Sub-Account Management

See `docs/brainstorm/BYBIT_SUB_ACCOUNTS.md` for API details.

### Lifecycle

```
Promote to Live:
  1. Create sub-account (or reuse existing)
  2. Generate API key pair
  3. Transfer initial capital from master
  4. Start LiveRunner with sub-account credentials
  5. Monitor performance

Demote from Live:
  1. Close all positions (reduce_only)
  2. Stop LiveRunner
  3. Transfer remaining capital back to master
  4. Freeze sub-account (optional)
```

### Capital Allocation Strategy

```python
class CapitalAllocator:
    """Decide how much capital each live play gets."""

    def allocate(
        self,
        total_available: float,
        plays: list[PlayScore],
        max_per_play: float = 0.20,  # Max 20% of total per play
    ) -> dict[str, float]:
        """Allocate capital proportional to composite score."""
        total_score = sum(p.composite for p in plays)

        allocations = {}
        for play in plays:
            share = play.composite / total_score
            amount = min(total_available * share, total_available * max_per_play)
            allocations[play.play_id] = round(amount, 2)

        return allocations
```

---

## Results Storage

### Per-Play Record

Each play accumulates results across stages:

```json
{
  "play_id": "ema_cross_12_100_low",
  "factory_run": "run_20260225_143000",
  "template": "ema_crossover",
  "params": {
    "ema_fast": 12,
    "ema_slow": 100,
    "exec": "low_tf",
    "tp_pct": 2.0,
    "sl_pct": 1.0
  },
  "stages": {
    "backtest_synthetic": {
      "status": "passed",
      "sharpe": 1.45,
      "max_dd": 12.3,
      "trades": 34,
      "completed_at": "2026-02-25T14:35:00"
    },
    "backtest_real": {
      "status": "passed",
      "sharpe": 1.22,
      "max_dd": 15.1,
      "trades": 28,
      "completed_at": "2026-02-25T14:40:00"
    },
    "live_sim": {
      "status": "running",
      "current_sharpe": 1.18,
      "current_dd": 3.2,
      "trades_so_far": 8,
      "started_at": "2026-02-25T16:00:00",
      "days_active": 3
    }
  },
  "current_stage": "live_sim",
  "promotions": [
    {"from": "backtest_synthetic", "to": "backtest_real", "at": "2026-02-25T14:35:00"},
    {"from": "backtest_real", "to": "live_sim", "at": "2026-02-25T16:00:00"}
  ],
  "demotions": []
}
```

### Leaderboard Query

```bash
# Current live sim leaderboard
python trade_cli.py factory leaderboard --stage live_sim

# Historical winners
python trade_cli.py factory leaderboard --stage live --since 2026-01-01

# Detailed play history
python trade_cli.py factory history --play ema_cross_12_100_low
```

---

## CLI Commands (Full Set)

```bash
# Generation
python trade_cli.py factory generate --grid <grid_id>
python trade_cli.py factory generate --grid <grid_id> --sample 200

# Backtesting
python trade_cli.py factory backtest --run <run_id>                    # All plays
python trade_cli.py factory backtest --run <run_id> --stage real       # Real data only
python trade_cli.py factory filter --run <run_id> --min-sharpe 1.0     # Apply filter

# Live Sim
python trade_cli.py factory live-sim start --run <run_id> --top 20     # Start top 20
python trade_cli.py factory live-sim stop --run <run_id>               # Stop all
python trade_cli.py factory live-sim stop --play <play_id>             # Stop one

# Monitoring
python trade_cli.py factory status --run <run_id>                      # Overview
python trade_cli.py factory leaderboard --stage live_sim               # Rankings
python trade_cli.py factory history --play <play_id>                   # Play history

# Promotion
python trade_cli.py factory promote --play <play_id> --to demo        # Manual promote
python trade_cli.py factory demote --play <play_id>                   # Manual demote
python trade_cli.py factory auto-promote --run <run_id>               # Auto-promote eligible

# Sub-account management (wraps Bybit API)
python trade_cli.py factory account create --play <play_id> --capital 1000
python trade_cli.py factory account fund --play <play_id> --amount 500
python trade_cli.py factory account recall --play <play_id>
python trade_cli.py factory account status
```
