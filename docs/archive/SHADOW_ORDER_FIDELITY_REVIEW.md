# Shadow Exchange Order Fidelity Review

**Date:** 2026-02-27
**Scope:** SimulatedExchange vs Bybit V5 USDT Linear Perpetuals — order handling parity for Shadow Exchange (M4)

## Context

The Shadow Exchange (M4) runs the SimulatedExchange with a real WebSocket feed — there is NO live Bybit order API. The sim IS the exchange. Every Bybit order behavior we don't replicate is a fidelity gap that compounds over days/weeks of extended paper trading.

**Sources cross-referenced:**
- Bybit V5 API docs (`reference/exchanges/bybit/docs/v5/order/`)
- pybit SDK (`reference/exchanges/pybit/`)
- SimulatedExchange (`src/backtest/sim/exchange.py`, `types.py`, `execution_model.py`)
- Engine adapters (`src/engine/adapters/backtest.py`, `live.py`)
- Play DSL (`docs/PLAY_DSL_REFERENCE.md`)
- Live order modules (`src/core/exchange_orders_*.py`)

---

## What the Sim Gets RIGHT Today

| Feature | Status | Key Code |
|---------|--------|----------|
| Market order fills (bar open + slippage) | Correct | `execution_model.py:fill_entry_order()` |
| Limit order fills (price touch + improvement) | Correct | `execution_model.py:fill_limit_order()` |
| Stop-market / stop-limit triggers | Correct | `types.py:OrderBook.check_triggers()` |
| GTC / IOC / FOK / PostOnly TIF | Correct | `execution_model.py:fill_limit_order()` |
| Maker vs taker fee routing | Correct | Limit=maker, market/SL=taker, limit TP=maker |
| OCO behavior (TP cancels SL implicitly) | Correct | Position-level TP/SL, close nulls both |
| Liquidation on mark price | Correct | `exchange.py:_check_liquidation()` |
| Bankruptcy price settlement | Correct | `liquidation_model.py:calculate_bankruptcy_price()` |
| Funding rate (`pos_value x rate x direction`) | Correct | `funding_model.py`, 8h intervals |
| Reduce-only enforcement | Correct | `execution_model.py:check_reduce_only()` |
| Break-even stop | Correct | `exchange.py:update_break_even_stop()` (better than Bybit native) |
| Deterministic fills (sequential IDs) | Correct | No PYTHONHASHSEED dependency |
| Order amendment (price/qty/TP/SL) | Correct | `types.py:OrderBook.amend_order()` |
| 1m granular TP/SL checking | Correct | `intrabar_path.py:check_tp_sl_1m()` |

---

## Bybit Features That DON'T Apply to Shadow

| Feature | Why N/A |
|---------|---------|
| DCP (Disconnect Cancel All) | No real connection to lose |
| Self-Match Prevention (`smpType`) | Single actor, can't self-match |
| BBO orders (`bboSideType`) | No real order book to reference |
| API slippage tolerance (`slippageTolerance`) | Sim controls slippage directly |
| `isLeverage` (spot margin) | Perps only |
| `orderFilter` (spot) | Perps only |
| RPI time-in-force | Market maker only |
| Batch operations | Sim processes orders synchronously |

---

## HIGH-Severity Gaps

### H1: No Mark Price / Last Price Divergence

**What Bybit does:**
- `markPrice = median(lastPrice, indexPrice, movingAvgBasis)` — independent price stream
- Mark price can diverge 0.1-2% from last price during volatile conditions, liquidation cascades, or thin books
- Mark price drives: liquidation trigger, maintenance margin, unrealized PnL, funding calculation
- Last price drives: default TP/SL triggers, order fills
- WS ticker topic `tickers` pushes both `lastPrice` and `markPrice` in real-time

**What the sim does:**
- `PriceSnapshot` (`src/backtest/sim/types.py:377-403`) has both `mark_price` and `last_price` fields — data structures are ready
- `PriceModel.get_prices()` (`src/backtest/sim/pricing/price_model.py:100-135`) derives BOTH from the same OHLC bar:
  - `last_price` = `bar.close` always (line 82)
  - `mark_price` = configurable: `close` (default), `hlc3`, `ohlc4` (lines 58-68) — but still derived from the same bar
- `TickerData` (`src/data/realtime_models.py:75-183`) ingests both from WS via `from_bybit()` (line 97-117) — WS plumbing already works
- Liquidation check (`exchange.py:704-753`) correctly uses `mark_price` only — this is right
- Ledger unrealized PnL (`ledger.py`) uses `mark_price` — this is right
- BUT: in backtest mode, mark == last == bar.close derivatives, so there's zero divergence

**Shadow impact:** The WS ticker delivers real `markPrice` and `lastPrice` separately. Without feeding real mark price into the sim:
- Liquidation timing drifts (mark price is smoother, last price wicks more)
- Margin headroom calculation is wrong (uses bar-derived mark, not exchange mark)
- Unrealized PnL tracking diverges from what Bybit dashboard shows
- Compounds across extended shadow runs (days/weeks)

**What needs to change:**
1. `PriceModel` needs `set_external_prices(mark: float, last: float, index: float)` — shadow mode feeds real WS prices instead of deriving from OHLC
2. `SimulatedExchange.process_bar()` in shadow mode: accept external price overrides alongside the bar
3. Liquidation, margin, and unrealized PnL already use `mark_price` correctly — just need the real value fed in

---

### H2: TP/SL Can't Trigger on Mark vs Last vs Index Price

**What Bybit does:**
- `tpTriggerBy` and `slTriggerBy` parameters on every order — independently configurable per TP and SL
- Valid values: `LastPrice` (default), `MarkPrice`, `IndexPrice`
- Same `triggerBy` parameter on conditional (stop) orders
- Mark-price SL is standard practice to prevent wick-based false stops
- pybit: `place_order(tpTriggerBy="MarkPrice", slTriggerBy="LastPrice", ...)` — fully supported

**What the sim does:**
- `check_tp_sl()` in `intrabar_path.py:132-184`:
  ```python
  # LONG: SL triggers on bar.low, TP triggers on bar.high
  if sl is not None and bar.low <= sl:   # Always bar.low — no price source param
      return FillReason.STOP_LOSS
  if tp is not None and bar.high >= tp:  # Always bar.high — no price source param
      return FillReason.TAKE_PROFIT
  ```
- `check_tp_sl_1m()` in `intrabar_path.py:215-259` — same pattern, iterates 1m bars but always uses OHLC
- `OrderBook.check_triggers()` in `types.py:787` — stop orders use `bar.high`/`bar.low` only
- No `trigger_by` field exists on `Order` (`types.py`), `Position` (`types.py`), or anywhere in the trigger chain
- `TriggerDirection` enum exists (`types.py`) for rise/fall direction but not for price source selection

**Shadow impact:**
- In real markets, mark price filters out wicks. A 2-second wick to $58k on BTC might show `bar.low = 58000` but `markPrice` never drops below $59k
- Without mark-price triggers, shadow produces phantom stop-outs on wicks that Bybit's mark price would ignore
- Results in falsely pessimistic shadow performance — strategies appear to lose more than they would on the real exchange
- Particularly impactful during liquidation cascades and flash wicks

**What needs to change:**
1. Add `trigger_by: Literal["LastPrice", "MarkPrice", "IndexPrice"]` to `Position` TP/SL fields and `Order` type
2. `check_tp_sl()` receives the current mark/last/index prices and compares TP against `tp_trigger_by` source, SL against `sl_trigger_by` source
3. `check_triggers()` for stop orders: same pattern — compare trigger_price against the configured price source
4. Play DSL: `risk_model.tp_trigger_by: "LastPrice"`, `risk_model.sl_trigger_by: "MarkPrice"`

---

### H3: No Partial TP/SL (Split Exits)

**What Bybit does:**
- `tpslMode: "Partial"` on `place_order()` — TP/SL close only part of the position
- `tpSize` / `slSize` on `set_trading_stop()` — specify exact qty to close
- Multiple TP levels via separate conditional orders:
  - TP1 at 1R -> close 50% (`create_conditional_order(qty=half, triggerPrice=tp1, reduceOnly=True)`)
  - TP2 at 2R -> close 30%
  - TP3 at 3R -> close 20%
- When a partial TP fires, position size reduces but position stays open
- Remaining TP/SL orders stay active with their original sizes
- Full-mode TP/SL (`tpslMode: "Full"`) closes entire position — current sim behavior

**What the sim does:**
- `Position` in `types.py:215-216`:
  ```python
  stop_loss: float | None = None       # Single price, no size
  take_profit: float | None = None     # Single price, no size
  ```
- `_check_tp_sl_exits()` in `exchange.py:629` -> calls `_close_position()` which closes 100% always
- `_close_position()` at `exchange.py:1096` — sets `self.position = None` after exit
- `_partial_close_position()` EXISTS at `exchange.py:1130-1200` — reduces position size, adjusts entry tracking, creates partial trade record — BUT it is only called by signal-based closes, NEVER by TP/SL triggers
- The machinery for partial closes is built; it's just not wired to TP/SL

**Shadow impact:**
- Split-TP is the #1 standard professional trade management pattern
- "Take half at 1R, trail the rest" is used by virtually every serious trader
- Any play using scaled exits behaves fundamentally differently — full close at TP1 instead of partial
- This changes win rate, average win, and risk-reward metrics dramatically
- **This is the largest behavioral divergence between sim and Bybit**

**What needs to change:**
1. New dataclass `TpSlLevel`:
   ```python
   @dataclass
   class TpSlLevel:
       price: float
       size_pct: float              # 0.0-100.0, what % of position to close
       order_type: str = "Market"   # "Market" | "Limit"
       trigger_by: str = "LastPrice"
       limit_price: float | None = None  # For order_type="Limit" when trigger != fill price
       triggered: bool = False      # Track which levels have fired
   ```
2. Replace `Position.take_profit`/`stop_loss` with `tp_levels: list[TpSlLevel]`, `sl_levels: list[TpSlLevel]`
3. Backward compat: single TP/SL still works as `[TpSlLevel(price=X, size_pct=100.0)]`
4. `_check_tp_sl_exits()` iterates levels, finds triggered ones, calls `_partial_close_position()` for `size_pct < 100`
5. After partial close: mark level as `triggered=True`, don't remove remaining levels
6. When all TP levels triggered or position fully closed -> clear position

---

### H4: No Dynamic TP/SL Modification Post-Entry

**What Bybit does:**
- `set_trading_stop()` endpoint (`/v5/position/trading-stop`) modifies on any open position:
  - `takeProfit`, `stopLoss` — new price levels
  - `tpSize`, `slSize` — new close quantities
  - `trailingStop` — trailing distance in price units
  - `activePrice` — activation price for trailing
  - `tpTriggerBy`, `slTriggerBy` — trigger source changes
  - `tpLimitPrice`, `slLimitPrice` — limit fill prices
  - `tpOrderType`, `slOrderType` — Market or Limit
- Can be called any time, any number of times
- Strategies routinely: tighten stops after favorable move, move TP after structure change, switch from fixed SL to trailing after reaching 1R

**What the sim does:**
- TP/SL are set at entry time in `_handle_entry_fill()` (`exchange.py:1004-1048`) and never change UNLESS:
  - `update_trailing_stop()` (`exchange.py:1348`) — built-in trailing logic, activates after `activation_pct` profit
  - `update_break_even_stop()` (`exchange.py:1430`) — moves SL to entry + offset, fires once
- Both are called from `_update_dynamic_stops()` (`exchange.py:602`) each bar — hardcoded behavior, not strategy-controlled
- No public API for arbitrary TP/SL modification: no `modify_position_tp_sl()`, no `set_trading_stop()` equivalent
- The strategy evaluation layer (DSL) has no mechanism to emit "modify stops" signals — only entry/exit/flat

**Shadow impact:**
- Any strategy that adjusts exits based on evolving market conditions cannot be faithfully simulated
- Examples that break: "move SL to breakeven after 1R" (partially covered by BE stop), "tighten SL when structure breaks" (not possible), "add trailing after TP1 fills" (not possible), "widen SL during high volatility" (not possible)
- Forces strategies into static exit designs, which is not how professional trading works

**What needs to change:**
1. Add `modify_position_stops()` to `SimulatedExchange`:
   ```python
   def modify_position_stops(
       self,
       stop_loss: float | None = None,
       take_profit: float | None = None,
       trailing_stop: float | None = None,
       active_price: float | None = None,
       tp_trigger_by: str | None = None,
       sl_trigger_by: str | None = None,
   ) -> bool:
   ```
2. Add a DSL action type for stop modification (e.g., `modify_sl`, `modify_tp`) or an engine hook
3. PlayEngine adapter (both backtest and shadow) routes modify requests to the sim

---

## MEDIUM-Severity Gaps

### M1: No `closeOnTrigger` Support

**What Bybit does:**
- `closeOnTrigger=true` on conditional orders (create-order.mdx line 79)
- When the order triggers but margin is insufficient: Bybit cancels or reduces OTHER active orders of the same contract to free up margin
- Stronger guarantee than `reduceOnly` — it actively fights for margin to ensure the stop fires
- Standard safety pattern for stop-loss orders in production trading
- Only valid for linear & inverse, not spot

**What the sim does:**
- `reduce_only` flag on `Order` (`types.py:126`) — prevents position expansion but doesn't cancel competing orders
- `check_reduce_only()` in `execution_model.py:640-679` — validates position exists and order is opposite side
- If margin is insufficient when SL triggers: order is REJECTED with `INSUFFICIENT_MARGIN` code
- No mechanism to cancel other pending orders to free margin for the SL
- In single-position scenarios this rarely matters; in multi-order scenarios (conditional entries pending + SL) it can cause SL failure

**What needs to change:**
1. Add `close_on_trigger: bool` field to `Order` dataclass
2. In `_process_order_book()`, when a `close_on_trigger` order triggers and margin check fails:
   - Cancel all non-reduce-only pending orders for the same symbol
   - Recompute available margin
   - Retry the fill
3. Wire through DSL: `risk_model.close_on_trigger: true` (default for SL orders)

---

### M2: No Partial Fills on Limit Orders

**What Bybit does:**
- Limit orders match against the real order book — can fill partially
- `PartiallyFilled` status: order stays active with reduced `leavesQty`
- IOC: fills what it can immediately, cancels unfilled remainder
- FOK: fills entirely or cancels entirely — no partial
- Response includes `cumExecQty` (filled so far) and `leavesQty` (remaining)

**What the sim does:**
- `fill_limit_order()` in `execution_model.py:328-436` — all-or-nothing
- Comment at line 137-138: `"partial fills not implemented — would require order splitting"`
- `LiquidityModel` exists (`src/backtest/sim/execution/liquidity_model.py`) but is a no-op by default
- IOC and FOK behave identically (line 386-395: "Since we don't do partial fills, this is same as IOC")
- `OrderStatus` enum has: `PENDING`, `FILLED`, `CANCELLED`, `REJECTED` — no `PARTIALLY_FILLED`

**What needs to change:**
1. Add `PARTIALLY_FILLED` to `OrderStatus` enum
2. Add `filled_qty` and `remaining_qty` fields to `Order`
3. `LiquidityModel` should estimate fillable depth from volume or configurable depth profile
4. `fill_limit_order()` fills up to available depth, moves to `PARTIALLY_FILLED` if remainder
5. IOC: fill what's available, cancel remainder. FOK: reject if full qty not available
6. Shadow mode: could use real WS order book snapshots for depth estimation

---

### M3: Trailing Stop Uses Percentage, Not Absolute `activePrice`

**What Bybit does:**
- `set_trading_stop(trailingStop="50", activePrice="70000")` — absolute price values
- `trailingStop` = fixed price distance in quote currency (e.g., $50 from peak)
- `activePrice` = absolute price level where trailing begins (e.g., $70,000)
- No percentage-based or ATR-based trailing natively

**What the sim does:**
- `update_trailing_stop()` in `exchange.py:1348-1420`:
  - `activation_pct` — percentage of profit from entry (e.g., 0.5 = 0.5% profit)
  - `trail_pct` — trailing distance as percentage (e.g., 0.3 = 0.3%)
  - Also supports `trail_atr_multiple` — ATR-based trailing (Bybit doesn't have this)
  - Activation check (line 1391): `profit_pct >= activation_pct` — percentage, not absolute price
  - `pos.trailing_active` tracks activation state (line 1396)
  - Trail calc (line 1400): `new_sl = peak * (1 - trail_pct/100)` for longs

**What needs to change:**
1. Add `active_price: float | None` field alongside `activation_pct` on trailing config
2. If `active_price` is set, check `current_price >= active_price` (long) instead of percentage
3. Add `trail_distance: float | None` alongside `trail_pct` — fixed price distance option
4. Keep percentage and ATR modes as TRADE-specific extensions (useful for backtest even though Bybit doesn't have them)
5. Play DSL: `trailing_stop.active_price: 70000`, `trailing_stop.distance: 50`

---

## LOW-Severity Gaps (defer to post-M4)

| Gap | Detail | Affected Code |
|-----|--------|---------------|
| `tpLimitPrice`/`slLimitPrice` | Bybit: trigger price and limit fill price can differ. Sim: trigger price IS the fill price. Affects only `tpOrderType: "Limit"` fills. Minor fill price difference (<0.1%). | `execution_model.py:fill_exit()` line 549 |
| `triggerBy` on stop orders | Conditional order triggers hardcoded to bar OHLC (`types.py:787`). No MarkPrice/IndexPrice option. Covered by H2 fix — same pattern. | `types.py:OrderBook.check_triggers()` |
| Live adapter limit/stop routing | `LiveExchange.submit_order()` in `src/engine/adapters/live.py` only routes market orders. Limit/stop exist in `src/core/exchange_orders_limit.py` and `exchange_orders_stop.py` but not wired through engine adapter. Only matters for M5 (live sub-accounts), not M4 (shadow). | `src/engine/adapters/live.py:submit_order()` |
| Order expiry `expire_after_bars` in live | DSL supports bar-based expiry in backtest sim, but live adapter doesn't implement it. Shadow sim handles this correctly via `OrderBook` expiry tracking. | `types.py:Order.submission_bar_index` |
| `tpslMode` amend | Bybit allows amending `tpslMode` on existing orders. Sim `amend_order()` doesn't support changing tpslMode. Rarely used. | `types.py:OrderBook.amend_order()` |

---

## Full Bybit Order Type Support Matrix

### Order Types

| Order Type | Bybit API | pybit Method | Sim (Backtest) | Live (Core) | Engine Adapter | Play DSL |
|-----------|-----------|-------------|:-:|:-:|:-:|:-:|
| Market | `orderType: "Market"` | `place_order()` | Y | Y | Y | Y |
| Limit | `orderType: "Limit"` | `place_order()` | Y | Y | Y | Y |
| Conditional (Stop Market) | `triggerPrice` + `triggerDirection` | `place_order()` | Y | Y | Y | - |
| Conditional (Stop Limit) | `triggerPrice` + `price` | `place_order()` | Y | Y | Y | - |

### Time-In-Force

| TIF | Bybit | Sim | Live | DSL |
|-----|:-----:|:---:|:----:|:---:|
| GTC | Y | Y | Y | Y |
| IOC | Y | Y | Y | Y |
| FOK | Y | Y | Y | Y |
| PostOnly | Y | Y | Y | Y |
| RPI | Y (market makers) | - | - | - |

### TP/SL Features

| Feature | Bybit | Sim | Live | DSL |
|---------|:-----:|:---:|:----:|:---:|
| TP/SL on entry order | Y | Y | Y | Y |
| tpslMode Full | Y | Y (default) | Y | Y |
| tpslMode Partial | Y | **GAP H3** | Y (core) | - |
| tpLimitPrice / slLimitPrice | Y | **GAP (LOW)** | - | - |
| tpOrderType Market/Limit | Y | Y | Y | Y |
| slOrderType Market/Limit | Y | Y | Y | Y |
| tpTriggerBy (Last/Mark/Index) | Y | **GAP H2** | - | - |
| slTriggerBy (Last/Mark/Index) | Y | **GAP H2** | - | - |
| set_trading_stop() | Y | **GAP H4** | - | - |
| Trailing stop (distance) | Y | Y (pct-based) | - | Y |
| activePrice (absolute) | Y | **GAP M3** | - | - |
| OCO (TP cancels SL) | Y | Y (implicit) | Y | Y |

### Order Management

| Feature | Bybit | Sim | Live |
|---------|:-----:|:---:|:----:|
| Amend order (price/qty) | Y | Y | Y |
| Amend TP/SL on order | Y | Y | Y |
| Cancel single order | Y | Y | Y |
| Cancel all orders | Y | Y | Y |
| Get open orders | Y | Y (internal) | Y |
| Order history (2yr) | Y | - | Y |
| Execution history | Y | - | Y |
| Batch place (10 max) | Y | - | Y |
| Batch amend (10 max) | Y | - | Y |
| Batch cancel (10 max) | Y | - | Y |

### Execution Features

| Feature | Bybit | Sim | Live |
|---------|:-----:|:---:|:----:|
| Partial fills | Y | **GAP M2** | Y (native) |
| reduceOnly | Y | Y | Y |
| closeOnTrigger | Y | **GAP M1** | - |
| smpType (self-match prevention) | Y | N/A | - |
| Slippage tolerance | Y | Fixed BPS | - |
| BBO orders | Y | N/A | - |
| DCP (disconnect cancel all) | Y | N/A | Y |

### Price Model

| Feature | Bybit | Sim |
|---------|:-----:|:---:|
| Mark price (independent stream) | Y | **GAP H1** |
| Last price | Y | Y (bar.close) |
| Index price | Y | - |
| Mark/Last/Index for triggers | Y | **GAP H2** |
| Mark price for liquidation | Y | Y (correct, needs real feed) |
| Mark price for unrealized PnL | Y | Y (correct, needs real feed) |

---

## Implementation Phases

### Phase 1: Price Fidelity (H1 + H2)

**Goal:** Sim accepts external mark/last/index prices from WS, TP/SL trigger against configurable price source.

**Files to modify:**
- `src/backtest/sim/pricing/price_model.py` — add external price override
- `src/backtest/sim/types.py` — add `trigger_by` to Order, Position, new `TriggerSource` enum
- `src/backtest/sim/pricing/intrabar_path.py` — `check_tp_sl()` accepts price sources
- `src/backtest/sim/exchange.py` — `process_bar()` passes prices through to TP/SL checks
- `src/backtest/play/play.py` — add `tp_trigger_by`, `sl_trigger_by` fields
- `src/engine/adapters/backtest.py` — pass trigger_by through to sim

**Tasks:**
- [ ] Add `TriggerSource` enum: `LAST_PRICE`, `MARK_PRICE`, `INDEX_PRICE` to `types.py`
- [ ] Add `trigger_by` field to `Order` dataclass (default `LAST_PRICE`)
- [ ] Add `tp_trigger_by`, `sl_trigger_by` fields to `Position` dataclass (default `LAST_PRICE`)
- [ ] Add `set_external_prices(mark, last, index)` method to `PriceModel`
- [ ] When external prices are set, `get_prices()` returns them instead of OHLC-derived values
- [ ] Modify `check_tp_sl()` signature: add `mark_price`, `last_price`, `index_price` params
- [ ] TP checks against `tp_trigger_by` source; SL checks against `sl_trigger_by` source
- [ ] Modify `check_tp_sl_1m()` similarly — for shadow mode, 1m bars still use OHLC but mark price overrides are respected for trigger comparison
- [ ] `OrderBook.check_triggers()`: use `trigger_by` field on each stop order
- [ ] `exchange.py:process_bar()` passes all three prices to `_check_tp_sl_exits()` and `_process_order_book()`
- [ ] Add `tp_trigger_by`, `sl_trigger_by` to Play DSL in `play.py` risk_model section
- [ ] Propagate through `BacktestExchange.submit_order()` in adapter
- [ ] Default: `tp_trigger_by="LastPrice"`, `sl_trigger_by="LastPrice"` (matches Bybit default)
- [ ] **GATE**: `python trade_cli.py validate quick` passes — existing behavior unchanged when trigger_by not set
- [ ] **GATE**: New validation play: `SIM_PRICE_001` — test that mark-price SL ignores wick below SL when mark stays above
- [ ] **GATE**: New validation play: `SIM_PRICE_002` — test index-price trigger for stop orders

### Phase 2: Exit Fidelity (H3 + H4)

**Goal:** Position supports multiple TP/SL levels with partial closes. Strategy layer can modify stops post-entry.

**Files to modify:**
- `src/backtest/sim/types.py` — new `TpSlLevel` dataclass, replace single TP/SL on Position
- `src/backtest/sim/exchange.py` — `_check_tp_sl_exits()` iterates levels, partial close wiring
- `src/backtest/sim/execution/execution_model.py` — `fill_exit()` handles partial size
- `src/backtest/play/play.py` — split-TP DSL syntax
- `src/engine/play_engine.py` — modify stops action type

**Tasks:**
- [ ] New `TpSlLevel` dataclass in `types.py`:
  ```python
  @dataclass(slots=True)
  class TpSlLevel:
      price: float
      size_pct: float              # 0-100, portion of position to close
      order_type: str = "Market"   # "Market" | "Limit"
      trigger_by: str = "LastPrice"
      limit_price: float | None = None
      triggered: bool = False
  ```
- [ ] Replace `Position.take_profit: float | None` with `Position.tp_levels: list[TpSlLevel]`
- [ ] Replace `Position.stop_loss: float | None` with `Position.sl_levels: list[TpSlLevel]`
- [ ] Backward compat: single TP/SL -> `[TpSlLevel(price=X, size_pct=100.0)]`
- [ ] Keep `Position.take_profit` and `.stop_loss` as computed properties returning first level price (for logging/display)
- [ ] `_check_tp_sl_exits()` iterates `tp_levels` + `sl_levels`:
  - For each untriggered level, check if price crosses level price (using level's `trigger_by`)
  - If triggered and `size_pct < 100`: call `_partial_close_position(percent=level.size_pct)`
  - If triggered and `size_pct == 100` (or cumulative 100%): call `_close_position()`
  - Mark level `triggered = True`
- [ ] `_partial_close_position()` already exists (`exchange.py:1130-1200`) — verify it handles fee calc, ledger update, trade record correctly for TP/SL-driven partials
- [ ] `fill_exit()` in execution model: accept `size_pct` parameter, compute partial notional
- [ ] Add `modify_position_stops()` to `SimulatedExchange`:
  ```python
  def modify_position_stops(
      self,
      stop_loss: float | None = None,
      take_profit: float | None = None,
      tp_levels: list[TpSlLevel] | None = None,
      sl_levels: list[TpSlLevel] | None = None,
      trailing_stop: float | None = None,
      active_price: float | None = None,
  ) -> bool:
  ```
- [ ] Update Play DSL to express split TPs:
  ```yaml
  risk_model:
    take_profit:
      - { level: 1.5, size_pct: 50, order_type: "Limit", trigger_by: "LastPrice" }
      - { level: 2.5, size_pct: 30, order_type: "Market" }
      - { level: 4.0, size_pct: 20, order_type: "Market" }
    stop_loss:
      type: "atr_multiple"
      value: 1.5
      trigger_by: "MarkPrice"
  ```
- [ ] Ensure OCO behavior: when last SL level fires, cancel remaining TP levels (and vice versa)
- [ ] Update trailing/BE stop to work with new `sl_levels` list (modify first/primary SL level)
- [ ] Engine adapter: modify stops hook — DSL action type or engine callback for strategy-driven stop changes
- [ ] **GATE**: `python trade_cli.py validate quick` passes — single TP/SL backward compat
- [ ] **GATE**: New validation play: `SIM_SPLIT_001` — 3-level TP (50/30/20), verify 3 partial fills
- [ ] **GATE**: New validation play: `SIM_SPLIT_002` — SL fires after TP1, verify partial position closed at SL
- [ ] **GATE**: New validation play: `SIM_SPLIT_003` — modify SL post-entry via engine hook, verify new SL used
- [ ] **GATE**: Existing 229 synthetic plays still pass with new Position model

### Phase 3: Safety & Polish (M1 + M2 + M3)

**Goal:** closeOnTrigger, partial limit fills, absolute trailing activation.

**Files to modify:**
- `src/backtest/sim/exchange.py` — closeOnTrigger margin logic
- `src/backtest/sim/execution/execution_model.py` — partial fill splitting
- `src/backtest/sim/types.py` — `PARTIALLY_FILLED` status, fill tracking fields
- `src/backtest/sim/execution/liquidity_model.py` — depth estimation (currently no-op)

**Tasks:**
- [ ] Add `close_on_trigger: bool = False` to `Order` dataclass
- [ ] In `_process_order_book()`: when a `close_on_trigger` order triggers and margin check fails:
  - Cancel all non-reduce-only pending orders for the same symbol
  - Recompute `available_balance_usdt` from ledger
  - Retry the fill with freed margin
  - Log the margin-rescue event
- [ ] Wire `close_on_trigger` through DSL: `risk_model.close_on_trigger: true` (default for SL)
- [ ] Add `PARTIALLY_FILLED` to `OrderStatus` enum
- [ ] Add `filled_qty: float = 0.0` and `remaining_qty: float` to `Order` dataclass
- [ ] `fill_limit_order()`: estimate fillable depth from `LiquidityModel`
  - If `fillable < order.size_usdt`: fill partial, move to `PARTIALLY_FILLED`, keep in book
  - IOC: fill available, cancel remainder
  - FOK: reject if full qty not available (currently correct behavior)
- [ ] `LiquidityModel.estimate_depth()`: configurable depth profile (e.g., based on bar volume or fixed depth curve)
- [ ] Trailing stop: add `active_price: float | None` alongside `activation_pct`
  - If `active_price` set: check `price >= active_price` (long) or `price <= active_price` (short)
  - If `activation_pct` set: existing percentage logic
  - Both can coexist (first condition met activates)
- [ ] Add `trail_distance: float | None` alongside `trail_pct` — fixed price distance mode
  - `new_sl = peak - trail_distance` (long) instead of percentage
- [ ] Update Play DSL: `trailing_stop.active_price`, `trailing_stop.distance`
- [ ] **GATE**: `python trade_cli.py validate standard` passes
- [ ] **GATE**: New validation play: `SIM_COT_001` — SL fires despite insufficient margin by canceling pending entry
- [ ] **GATE**: New validation play: `SIM_PARTIAL_001` — limit order partial fill, remainder stays active
- [ ] **GATE**: New validation play: `SIM_TRAIL_001` — absolute activePrice trailing stop activation
