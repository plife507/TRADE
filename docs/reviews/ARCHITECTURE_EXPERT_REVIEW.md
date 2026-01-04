# Architecture Expert Review

> **Date**: 2026-01-04
> **Reviewer**: Claude (Python + Quant perspective)
> **Scope**: Engine design, Live infrastructure, Hidden blockers

---

## Executive Summary

Your architecture is **surprisingly well-designed** for a non-developer project. The core patterns are correct, the modular structure is clean, and the hot-loop optimization shows good performance awareness. However, there are **critical gaps** between your simulator and live infrastructure that will bite you later.

| Aspect | Grade | Notes |
|--------|-------|-------|
| Engine Hot Loop | **A** | O(1) array access, no pandas in loop |
| Multi-TF Architecture | **A-** | Forward-fill semantics correct, clean |
| Blocks DSL | **B+** | Good foundation, needs limit order extensions |
| Simulated Exchange | **C+** | Works but single-order, no scaling |
| Live Infrastructure | **B-** | Has the pieces, not unified |
| Sim ↔ Live Parity | **D** | Major gap - different code paths |

---

## Part 1: What's Designed Well

### 1.1 Engine Hot Loop Architecture (A)

Your hot loop is **correctly optimized**:

```python
# engine.py:861-878 - O(1) bar access
for i in range(num_bars):
    ts_open = exec_feed.get_ts_open_datetime(i)  # O(1)
    ts_close = exec_feed.get_ts_close_datetime(i)  # O(1)

    bar = CanonicalBar(
        open=float(exec_feed.open[i]),   # Direct numpy indexing
        high=float(exec_feed.high[i]),
        low=float(exec_feed.low[i]),
        close=float(exec_feed.close[i]),
        volume=float(exec_feed.volume[i]),
    )
```

**What you got right**:
- FeedStore with precomputed numpy arrays
- No DataFrame operations in hot loop
- O(1) feature access via `exec_feed.indicators[key][i]`
- Incremental state updates per bar (O(1) structure detection)

**This is production-grade design.** Most trading systems get this wrong.

### 1.2 Multi-TF Forward-Fill Semantics (A-)

Your forward-fill logic is correct:

```python
# engine.py:1447-1481 - Forward-fill indices
def _update_htf_mtf_indices(self, exec_ts_close: datetime) -> tuple:
    """
    Forward-fill principle: Any TF slower than exec keeps its index constant
    until its bar closes. This ensures no-lookahead.
    """
```

**What you got right**:
- HTF/MTF indices only update on their bar close
- Lookahead guards with assertions (`assert snapshot.ts_close == bar.ts_close`)
- Data-driven close detection via `ts_close_ms_to_idx` maps
- Readiness gate blocks trading until caches are ready

**This prevents lookahead bias** - the #1 cause of backtest fantasy.

### 1.3 Modular Engine Decomposition

Your engine is well-factored into focused modules:

| Module | Responsibility | Lines |
|--------|----------------|-------|
| `engine.py` | Orchestration | ~1700 |
| `engine_data_prep.py` | Data loading | ~500 |
| `engine_feed_builder.py` | FeedStore construction | ~300 |
| `engine_snapshot.py` | Snapshot building | ~200 |
| `engine_stops.py` | Stop condition checking | ~150 |
| `engine_artifacts.py` | Result writing | ~100 |

**This is maintainable.** Each module has a single responsibility.

### 1.4 Blocks DSL Foundation (B+)

Your DSL is well-structured:

```python
# strategy_blocks.py - Clean Intent model
@dataclass(frozen=True)
class Intent:
    action: str
    metadata: dict[str, Any] = field(default_factory=dict)
```

**What you got right**:
- Immutable data structures (frozen dataclasses)
- Clear separation: Intent describes WHAT, engine handles HOW
- First-match case semantics (deterministic)
- Extensible via metadata dict

**The `metadata` field is key** - this is where limit order params will go.

---

## Part 2: What Needs Work

### 2.1 Simulated Exchange is Too Simple (C+)

**Current state** (`sim/exchange.py`):

```python
class SimulatedExchange:
    pending_order: Order | None = None  # ONLY ONE ORDER
    position: Position | None = None    # SINGLE ENTRY, NO LAYERS
```

**Problems**:
1. Can't have multiple pending orders (no limit order book)
2. Can't scale into positions (no layers)
3. Can't partially close (all-or-nothing)
4. Only market orders work

**This blocks all advanced strategies.**

### 2.2 Live Infrastructure is Disconnected (B-)

You have all the pieces, but they're not unified:

```
CURRENT STATE:

┌─────────────────────────────────────────────────────────────────┐
│ SIMULATOR PATH                │ LIVE PATH                      │
├───────────────────────────────┼────────────────────────────────┤
│ IdeaCard.blocks               │ ??? (not connected)            │
│ ↓                             │                                │
│ StrategyBlocksExecutor        │ ??? (not connected)            │
│ ↓                             │                                │
│ Intent objects                │ ??? (no intent processing)     │
│ ↓                             │                                │
│ engine._process_signal()      │ ExchangeManager.market_buy()   │
│ ↓                             │ ↓                              │
│ SimulatedExchange             │ BybitClient                    │
└───────────────────────────────┴────────────────────────────────┘
```

**The gap**: Live trading calls `ExchangeManager.market_buy()` directly - it doesn't go through the Blocks DSL or Intent system.

**What's needed**:

```
UNIFIED PATH:

┌─────────────────────────────────────────────────────────────────┐
│                        IdeaCard.blocks                          │
│                              ↓                                  │
│                   StrategyBlocksExecutor                        │
│                              ↓                                  │
│                       Intent objects                            │
│                              ↓                                  │
│                      IntentProcessor                            │
│                              ↓                                  │
│              ┌───────────────┴───────────────┐                  │
│              ▼                               ▼                  │
│     SimulatorBackend                  LiveBackend               │
│     (SimulatedExchange)               (ExchangeManager)         │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 No Unified Backend Protocol

**Missing abstraction**:

```python
# This doesn't exist yet
class ExecutionBackend(Protocol):
    async def submit_order(self, order: Order) -> OrderResult: ...
    async def cancel_order(self, order_id: str) -> bool: ...
    async def get_position(self) -> Position | None: ...
    async def get_equity(self) -> float: ...
```

Both `SimulatedExchange` and `ExchangeManager` have these methods, but with different signatures. You need a common interface.

---

## Part 3: Hidden Blockers (Unknown Unknowns)

These are things you wouldn't know to ask about:

### 3.1 🚨 CRITICAL: Async vs Sync Mismatch

**Your simulator is synchronous. Your live trading needs to be async.**

```python
# Simulator (sync)
def submit_order(self, side: str, size_usdt: float) -> OrderId:
    # Instant return - no network

# Live (needs to be async)
async def submit_order(self, order: Order) -> OrderResult:
    response = await self.client.place_order(...)  # Network call
    # Handle WebSocket updates
```

**Impact**: You can't just swap backends. The entire engine flow changes.

**Solution**: Design for async from the start. Even if simulator doesn't need it, make the interface async:

```python
class ExecutionBackend(Protocol):
    async def submit_order(self, order: Order) -> OrderResult: ...

class SimulatorBackend(ExecutionBackend):
    async def submit_order(self, order: Order) -> OrderResult:
        # Sync internally, but async interface
        result = self._exchange.submit_order(...)
        return result  # Immediate return, but async-compatible
```

### 3.2 🚨 CRITICAL: State Reconciliation

**Your simulator has perfect state. Live trading doesn't.**

```python
# Simulator: State is always consistent
assert self._exchange.position.size == expected_size  # Always true

# Live: State can drift
# - WebSocket disconnects → missed fill updates
# - REST call fails → stale position
# - Exchange lag → order filled but not reported yet
```

**You need a state reconciliation layer**:

```python
class StateReconciler:
    """Keeps local state in sync with exchange state."""

    async def reconcile(self):
        """Called periodically and after each operation."""
        exchange_position = await self.client.get_position(symbol)
        exchange_orders = await self.client.get_open_orders(symbol)

        # Compare to local state
        if self.local_position != exchange_position:
            self.logger.warning(f"Position drift detected: local={self.local_position}, exchange={exchange_position}")
            self.local_position = exchange_position
```

### 3.3 🚨 CRITICAL: Order State Machine

**Your simulator has binary order states: pending → filled.**

**Live trading has many states**:

```
NEW → PARTIALLY_FILLED → FILLED
  ↘ REJECTED
NEW → CANCELLED
NEW → EXPIRED
NEW → PARTIALLY_FILLED → CANCELLED
```

**You need to handle**:
- Partial fills (order 50% filled, then cancelled)
- Rejected orders (margin, price limits, etc.)
- Expired orders (GTC timeout, IOC unfilled portion)
- Amended orders (price change during pending)

### 3.4 🚨 Rate Limiting Awareness

**Your simulator has no rate limits. Live does.**

```python
# Current simulator: unlimited orders
for signal in signals:
    exchange.submit_order(...)  # No delay

# Live: Bybit limits
# - 10 orders/sec/symbol
# - 50 account queries/sec
# - 600 public requests/5sec
```

**If your strategy generates many signals quickly (grid trading, scalping), you'll hit limits.**

**Solution**: Build rate limiting into the Intent processor:

```python
class IntentProcessor:
    def __init__(self):
        self.order_limiter = RateLimiter(10, 1.0)  # 10/sec

    async def process(self, intent: Intent) -> OrderResult:
        await self.order_limiter.acquire()  # Wait if needed
        return await self.backend.submit_order(...)
```

### 3.5 🚨 Error Recovery

**Your simulator never fails. Live trading fails constantly.**

```python
# Things that can fail:
# - Network timeout
# - API rate limit exceeded
# - Insufficient margin (between check and submit)
# - Price moved (limit order immediately filled or rejected)
# - Symbol delisted/suspended
# - Maintenance mode
```

**You need retry logic with exponential backoff**:

```python
async def submit_with_retry(self, order: Order, max_retries: int = 3) -> OrderResult:
    for attempt in range(max_retries):
        try:
            return await self.backend.submit_order(order)
        except RateLimitError:
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
        except InsufficientMarginError:
            # Don't retry - condition won't change
            raise
        except NetworkError:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(1)
```

### 3.6 🚨 Clock Synchronization

**Your simulator has perfect time. Live trading doesn't.**

```python
# Simulator: Bar closes exactly at ts_close
bar.ts_close == datetime(2026, 1, 4, 12, 0, 0)  # Exactly midnight

# Live: Your clock might be off
# - System clock drift
# - Exchange server time differs
# - Network latency (you see bar 50ms late)
```

**Bybit provides server time** - you should sync:

```python
async def sync_clock(self):
    server_time = await self.client.get_server_time()
    local_time = datetime.now(UTC)
    self.clock_offset = server_time - local_time
    # Use this offset when comparing timestamps
```

### 3.7 WebSocket Reconnection

**Your simulator never disconnects. WebSockets do.**

```python
# Things that cause disconnects:
# - Server maintenance
# - Network issues
# - Idle timeout (Bybit: 30s without ping)
# - Rate limit ban
```

**You need reconnection logic with state recovery**:

```python
class ResilientWebSocket:
    async def connect(self):
        while True:
            try:
                await self._connect()
                await self._resubscribe()  # Re-subscribe to channels
                await self._reconcile_state()  # Sync missed updates
                await self._listen()
            except ConnectionClosed:
                self.logger.warning("WebSocket disconnected, reconnecting...")
                await asyncio.sleep(1)
```

---

## Part 4: Recommended Architecture

Here's the unified architecture that addresses all gaps:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           UNIFIED ENGINE                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                     IdeaCard YAML                                 │  │
│  │                   (Same for all modes)                            │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                  │                                      │
│                                  ▼                                      │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                  StrategyBlocksExecutor                           │  │
│  │              (Evaluates conditions, emits Intents)                │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                  │                                      │
│                                  ▼                                      │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                     IntentProcessor                               │  │
│  │     - Resolves dynamic price refs                                 │  │
│  │     - Validates order params                                      │  │
│  │     - Rate limiting                                               │  │
│  │     - Retry logic                                                 │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                  │                                      │
│                                  ▼                                      │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │               ExecutionBackend (Protocol)                         │  │
│  │  async submit_order(order) -> OrderResult                         │  │
│  │  async cancel_order(order_id) -> bool                             │  │
│  │  async get_position() -> Position | None                          │  │
│  │  async get_equity() -> float                                      │  │
│  │  async sync_state() -> None                                       │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                  │                                      │
│              ┌───────────────────┼───────────────────┐                  │
│              ▼                   ▼                   ▼                  │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐           │
│  │ SimulatorBackend│ │   DemoBackend   │ │   LiveBackend   │           │
│  ├─────────────────┤ ├─────────────────┤ ├─────────────────┤           │
│  │ SimulatedExch   │ │ BybitClient     │ │ BybitClient     │           │
│  │ (enhanced)      │ │ (demo endpoint) │ │ (live endpoint) │           │
│  │                 │ │ WebSocket       │ │ WebSocket       │           │
│  │ - Order book    │ │ StateReconciler │ │ StateReconciler │           │
│  │ - Fill sim      │ │ RateLimiter     │ │ RateLimiter     │           │
│  │ - Scaling       │ │ RetryHandler    │ │ RetryHandler    │           │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key Components to Build

| Component | Priority | Effort | Blocks |
|-----------|----------|--------|--------|
| **ExecutionBackend Protocol** | P0 | 1 day | Everything |
| **SimulatorBackend (enhanced)** | P1 | 3-4 days | Limit order testing |
| **IntentProcessor** | P1 | 2 days | Live execution |
| **LiveBackend wrapper** | P2 | 2-3 days | Live trading |
| **StateReconciler** | P2 | 2 days | Live reliability |
| **ResilientWebSocket** | P2 | 2 days | Live uptime |

---

## Part 5: Specific Code Issues

### 5.1 SimulatedExchange.submit_order Signature

**Current** (`sim/exchange.py:232`):
```python
def submit_order(
    self,
    side: str,              # Should be enum
    size_usdt: float,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    timestamp: datetime | None = None,
) -> OrderId | None:
```

**Needed**:
```python
async def submit_order(
    self,
    order: Order,           # Full order object
) -> OrderResult:           # Structured result
```

### 5.2 Missing Order Result Typing

**Current**: Returns `OrderId | None` (just a string or None)

**Needed**:
```python
@dataclass
class OrderResult:
    success: bool
    order_id: str | None = None
    filled_size: float = 0.0
    fill_price: float | None = None
    status: OrderStatus = OrderStatus.PENDING
    error: str | None = None
    rejection_reason: str | None = None
```

### 5.3 Intent → Order Mapping Missing

**Current**: Engine manually extracts signal params and calls `submit_order()`

**Needed**: Centralized Intent processor
```python
class IntentProcessor:
    def process(self, intent: Intent, snapshot: RuntimeSnapshotView) -> Order:
        """Convert Intent to Order with resolved refs."""
        meta = intent.metadata

        # Resolve dynamic price
        price = self._resolve_price(meta.get("price_ref"), snapshot)

        # Resolve size
        size = self._resolve_size(meta, snapshot.equity)

        return Order(
            side=self._intent_to_side(intent.action),
            order_type=meta.get("order_type", OrderType.MARKET),
            limit_price=price,
            size_usdt=size,
            ...
        )
```

---

## Part 6: Priority Roadmap

### Phase 0: Foundation (This Week)

- [ ] Define `ExecutionBackend` Protocol
- [ ] Define unified `Order` and `OrderResult` types
- [ ] Create `IntentProcessor` skeleton

### Phase 1: Enhanced Simulator (Week 2)

- [ ] `PendingOrderBook` for multiple orders
- [ ] Limit order fill simulation
- [ ] Position scaling (add/partial close)
- [ ] Stop order triggers

### Phase 2: Live Backend (Week 3)

- [ ] `LiveBackend` implementing `ExecutionBackend`
- [ ] Intent → Bybit order mapping
- [ ] State reconciliation
- [ ] Rate limiting

### Phase 3: Reliability (Week 4)

- [ ] WebSocket reconnection
- [ ] Error retry logic
- [ ] Clock sync
- [ ] Position drift detection

### Phase 4: Agent Integration (Week 5+)

- [ ] Agent consensus in snapshot builtins
- [ ] Forecast service integration
- [ ] Multi-agent decision pipeline

---

## Summary: Your Unknown Blockers

| Blocker | You Knew? | Severity | Fix Effort |
|---------|-----------|----------|------------|
| Async/sync mismatch | ❌ | 🔴 Critical | Medium |
| State reconciliation | ❌ | 🔴 Critical | Medium |
| Order state machine | ❌ | 🟡 High | Low |
| Rate limiting | ❌ | 🟡 High | Low |
| Error recovery | ❌ | 🟡 High | Medium |
| Clock sync | ❌ | 🟢 Medium | Low |
| WebSocket reconnection | ❌ | 🟡 High | Medium |
| Intent → Order mapping | Partial | 🟡 High | Medium |
| Unified backend protocol | ❌ | 🔴 Critical | Low |

**The good news**: Your foundation is solid. The fixes are additive, not rewrites.

**The work**: ~4-5 weeks to full simulator-live parity with reliability.

---

## Final Assessment

**As a Python expert**: Your code is clean, well-structured, and follows modern patterns. Type hints, dataclasses, modular design - all correct. The async gap is your biggest Python issue.

**As a quant**: Your backtest semantics are correct (no lookahead, closed-candle only, forward-fill). This is rare. Most systems get these wrong. Your engine is trustworthy for strategy validation.

**As a systems architect**: You have good bones, but you're missing the "production hardening" layer that handles the messy reality of live trading. That's normal - you haven't run live yet.

**Recommendation**: Focus on the `ExecutionBackend` protocol first. Once you have that abstraction, everything else plugs in cleanly.
