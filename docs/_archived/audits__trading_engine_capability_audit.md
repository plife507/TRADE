## Trading Engine Capability Audit

**Repository**: TRADE

**Scope**: Backtest/simulation trading pipeline capabilities (Signal→Order→Fill, SL/TP handling, exits, snapshot history access, artifacts, control flow, data auto-fetch)

---

## A. Signal → Order → Fill Pipeline

### A1) Is there a component that converts a `Signal` into an executable order?
**YES**.

- **File**: `src/backtest/engine.py`
- **Function**: `BacktestEngine._process_signal()`

Notes:
- Handles `Signal(direction="FLAT")` as a close request.
- Converts `LONG/SHORT` into `side` and submits an order to the simulated exchange.

### A2) What order types are supported in simulation?

**Defined (enum exists):**
- **File**: `src/backtest/sim/types.py`
- **Enum**: `OrderType`
  - `MARKET`
  - `LIMIT`
  - `STOP_MARKET`
  - `STOP_LIMIT`

**Actually used by the backtest engine entry path:**
- **MARKET entries only**
  - **File**: `src/backtest/sim/exchange.py`
  - **Method**: `SimulatedExchange.submit_order()` always sets `order_type=OrderType.MARKET`

**Close / reduce-only:**
- Implemented as a **pending close request**, not an order type
  - **File**: `src/backtest/sim/exchange.py`
  - **Method**: `SimulatedExchange.submit_close()`

### A3) Where is position quantity calculated from `size_usd` and price?
**YES**.

- **File**: `src/backtest/sim/execution/execution_model.py`
- **Function**: `ExecutionModel.fill_entry_order()`
- **Logic**: `size = order.size_usd / fill_price`

### A4) Does the engine support opening a position on signal automatically?
**YES**.

- **Signal handling / submit order**:
  - **File**: `src/backtest/engine.py`
  - **Function**: `BacktestEngine._process_signal()`
- **Entry fill** (at next bar open):
  - **File**: `src/backtest/sim/exchange.py`
  - **Method**: `SimulatedExchange.process_bar()` → `_fill_pending_order()`
- **Position created**:
  - **File**: `src/backtest/sim/exchange.py`
  - **Method**: `SimulatedExchange._fill_pending_order()`

Execution timing:
- Strategy decision at **bar close** (`ts_close`)
- Entry fills at **next bar open** (`ts_open`)

---

## B. Stop Loss / Take Profit Handling

### B5) Are `stop_loss` and `take_profit` in `Signal.metadata` actively used?
**YES**.

- **File**: `src/backtest/engine.py`
- **Function**: `BacktestEngine._process_signal()`
- Extracts `stop_loss` / `take_profit` from `signal.metadata` and passes them into `exchange.submit_order()`.

### B6) If yes, where are SL/TP evaluated?

**Evaluated on bar OHLC (high/low), not close-only.**

- **File**: `src/backtest/sim/pricing/intrabar_path.py`
- **Function**: `IntrabarPath.check_tp_sl()`
  - LONG: SL if `bar.low <= sl`, TP if `bar.high >= tp`
  - SHORT: SL if `bar.high >= sl`, TP if `bar.low <= tp`

Call site:
- **File**: `src/backtest/sim/exchange.py`
- **Method**: `SimulatedExchange.process_bar()` (step 5: check TP/SL)

### B7) Bracket orders vs manual monitoring?
**Manual monitoring per bar**.

- SL/TP are stored on the **Position** (`Position.stop_loss`, `Position.take_profit`).
- Each bar, `SimulatedExchange.process_bar()` checks TP/SL and closes if triggered.

### B8) If both SL and TP are crossed in the same candle, what happens first?
**Stop-loss wins (conservative tie-break: SL checked first).**

- **File**: `src/backtest/sim/pricing/intrabar_path.py`
- **Function**: `IntrabarPath.check_tp_sl()`

---

## C. Exit / Close Logic

### C9) Is there a native way to close an open position?
**YES**: `Signal(direction="FLAT")`.

- **File**: `src/backtest/engine.py`
- **Function**: `BacktestEngine._process_signal()`
  - If `signal.direction == "FLAT"`, calls `exchange.submit_close(reason="signal")`.

There is no special `EXIT` direction; the engine explicitly checks for `"FLAT"`.

### C10) Can a strategy force-close without SL/TP (e.g., EMA cross-down)?
**YES**.

Mechanism:
- Strategy returns `Signal(direction="FLAT")`
- Engine calls `SimulatedExchange.submit_close()`
- Exchange closes at next bar open

Relevant code:
- **File**: `src/backtest/engine.py` → `BacktestEngine._process_signal()`
- **File**: `src/backtest/sim/exchange.py` → `SimulatedExchange.submit_close()` and `SimulatedExchange.process_bar()` step 4

### C11) Where is the logic that finalizes a trade and records realized PnL?
**YES**.

- **File**: `src/backtest/sim/exchange.py`
- **Function**: `SimulatedExchange._close_position()`

It:
- Creates an exit fill (`ExecutionModel.fill_exit()`)
- Computes realized PnL (`ExecutionModel.calculate_realized_pnl()`)
- Applies ledger changes (`Ledger.apply_exit()`)
- Creates a `Trade` record (`src/backtest/types.py::Trade`) and appends it to `SimulatedExchange.trades`

---

## D. Bar & Indicator History Access

### D12) Does `RuntimeSnapshot` expose previous indicator values / previous bars / rolling window?
**NOT IMPLEMENTED**.

- **File**: `src/backtest/runtime/types.py`
- **Type**: `RuntimeSnapshot`
  - Exposes **current** `bar_ltf` and **current** `features_*` snapshots only.

### D13) If not, where should a strategy obtain previous EMA values / last N lows?
**As-is, there is no runtime-provided deterministic history inside `RuntimeSnapshot`.**

Practical options:
- **Strategy-managed state** (module/class state) to track previous EMA values and a rolling low window.
- **Runtime enhancement (recommended)**: extend snapshot construction to include prev features and/or a rolling bar window.

Snapshot is built here:
- **File**: `src/backtest/engine.py`
- **Function**: `BacktestEngine._build_snapshot()`
  - It only uses the **current** DataFrame row to populate `FeatureSnapshot.features`.

---

## E. Trade Recording & Artifacts

### E14) Where are executed trades stored?
- **File**: `src/backtest/sim/exchange.py`
- **Data structure**: `SimulatedExchange.trades` (list of `src/backtest/types.py::Trade`)

### E15) Are SL/TP prices recorded per trade in artifacts?
**PARTIAL**.

- **In-memory trade record**: **YES**
  - **File**: `src/backtest/types.py`
  - `Trade.stop_loss`, `Trade.take_profit` exist and are set in `SimulatedExchange._close_position()`.

- **`trades.csv` written by engine**: **NO** (does not include stop_loss/take_profit columns)
  - **File**: `src/backtest/engine.py`
  - Writer includes `trade_id`, `symbol`, `side`, times, entry/exit, qty, pnl, pnl_pct.

- **`result.json`**: **NO (by design)**
  - **File**: `src/backtest/types.py`
  - `BacktestResult.to_dict()` explicitly excludes trades/equity_curve (written to separate artifacts).

- **`events.jsonl`** (reconstructed by tools): **NO SL/TP fields logged**
  - **File**: `src/tools/backtest_tools.py`
  - **Function**: `_write_manifest_and_eventlog()` logs entry/exit “fill” events without SL/TP.

### E16) Is there a finalized “trade closed” event?
**NOT IMPLEMENTED** as a dedicated event type.

What exists:
- Tools reconstruct `events.jsonl` and emit "fill" events for entry and exit.
  - **File**: `src/tools/backtest_tools.py`
  - **Function**: `_write_manifest_and_eventlog()`

---

## F. Backtest Control Flow

### F17) Exact execution order per bar

**Prep (once per run):**
- Data loaded and indicators computed up-front
  - **File**: `src/backtest/engine.py`
  - **Function**: `BacktestEngine.prepare_backtest_frame()`
  - Calls `apply_core_indicators(df, params)`.

**Per bar (main loop):**
- **File**: `src/backtest/engine.py`
- **Function**: `BacktestEngine.run()`

Order (single-TF path):
1. Build canonical `Bar` with `ts_open` and `ts_close`
2. Exchange processes bar (fills/TP/SL/mark-to-market)
   - **File**: `src/backtest/sim/exchange.py`
   - **Method**: `SimulatedExchange.process_bar()`
3. Stop checks
4. Build `RuntimeSnapshot`
   - **File**: `src/backtest/engine.py`
   - **Function**: `BacktestEngine._build_snapshot()`
5. Strategy evaluation at bar close
   - Called as `strategy(snapshot, params)`
6. Signal processing (submit entry order / close request)
   - **File**: `src/backtest/engine.py`
   - **Function**: `BacktestEngine._process_signal()`
7. Record equity/account curve points

### F18) Does the engine guarantee closed-candle execution only?
**YES for strategy evaluation; entries/exits fill at bar open.**

- Strategy decisions are made after `process_bar()` and snapshot construction (using `ts_close`).
- Entry fills at next `ts_open` (pending order filled in `process_bar()`).

---

## G. Data Pipeline

### G19) What function pulls historical market data automatically?
For backtests, the auto-fetch/repair entry point is:

- **File**: `src/tools/backtest_tools.py`
- **Function**: `backtest_preflight_check_tool()`

It can trigger:
- `sync_full_from_launch_tool()` (bootstrap)
- `fill_gaps_tool()`
- `sync_range_tool()`
- `sync_funding_tool()`

### G20) Does the backtest runner auto-fetch missing data?
**YES (default)**, via preflight.

- **File**: `src/tools/backtest_tools.py`
- **Function**: `backtest_run_tool()`
  - Calls `backtest_preflight_check_tool()` when `run_preflight=True` (default) and heals when `heal_if_needed=True` (default).

---

## H. Missing Pieces / Partial Implementations

### H21) Missing/partial items

#### 1) Limit/Stop order execution (entry)
- **Status**: **PARTIAL / effectively NOT IMPLEMENTED in current engine path**
- **Evidence**:
  - Enum exists (`OrderType.LIMIT`, `STOP_MARKET`, `STOP_LIMIT`) in `src/backtest/sim/types.py`
  - Engine → exchange submission path always uses MARKET: `SimulatedExchange.submit_order()`
- **Impact**: backtests cannot place limit/stop entries through the current `Signal`→order path.
- **Minimum fix**:
  - Add entry submission variants supporting `order_type`, `limit_price`, `trigger_price`.
  - Implement corresponding fill logic in `ExecutionModel` and wire it from `SimulatedExchange.process_bar()`.

#### 2) Snapshot history (prev indicators / rolling bars)
- **Status**: **NOT IMPLEMENTED**
- **Impact**: true crossovers and “last N lows” cannot be computed from `RuntimeSnapshot` alone.
- **Minimum fix**:
  - Extend `RuntimeSnapshot` / `FeatureSnapshot` with `prev_features` and/or `bars_ltf_window`.
  - Populate in `BacktestEngine._build_snapshot()`.

#### 3) SL/TP recorded in primary artifacts
- **Status**: **PARTIAL**
- **Impact**: SL/TP exists on `Trade`, but not visible in `trades.csv` or logged in `events.jsonl`.
- **Minimum fix**:
  - Add `stop_loss` and `take_profit` columns to `trades.csv` writer in `BacktestEngine._write_artifacts()`.
  - Optionally include SL/TP in the `events.jsonl` fill reconstruction.

#### 4) “Trade closed” event
- **Status**: **NOT IMPLEMENTED** as distinct event.
- **Impact**: consumers must infer closure from an exit fill.
- **Minimum fix**:
  - Emit an explicit `trade_closed` event (engine-side or tool reconstruction).

---

## Final Summary

### H22) Can a simple EMA crossover strategy with SL/TP:

- **Open a trade?** **YES**
  - `BacktestEngine._process_signal()` submits an entry order; `SimulatedExchange.process_bar()` fills it next bar open.

- **Close via TP/SL?** **YES**
  - SL/TP are carried from `Signal.metadata` → `Order` → `Position` and checked every bar via OHLC.

- **Close via logic-based exit (EMA cross-down)?** **YES**
  - Strategy can emit `Signal(direction="FLAT")`, which triggers a close at next bar open.

### Critical limitation for “true crossover” and “lowest-low N lookback” strategies
- `RuntimeSnapshot` does **not** expose previous indicator values or bar windows (**NOT IMPLEMENTED**), so those requirements need either:
  - strategy-managed state, or
  - a runtime snapshot enhancement.
