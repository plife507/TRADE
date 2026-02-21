# Simulation Domain Review

> **STATUS (2026-02-18):** All findings resolved. 3 HIGH fixed, 2 MED fixed, 2 MED deferred (future features), 3 not-a-bug, 3 OK.
> See `FINDINGS_SUMMARY.md` for current status of each finding.

## Module Overview

 is the simulated exchange used for backtesting. It implements a Bybit-aligned USDT linear perpetual exchange (isolated margin mode). The domain is a thin orchestrator () that coordinates modular components: pricing, execution, funding, liquidation, ledger, metrics, and constraints.

The simulator runs on closed-candle OHLC data from the exec timeframe, with optional 1m granularity for more realistic TP/SL and entry fill simulation.

---

## File-by-File Findings

### types.py (~904 lines)

#### Summary
Core type definitions for the sim domain. Immutable frozen dataclasses where appropriate. All monetary fields use the `_usdt` suffix. `OrderBook` is a full order management system supporting market, limit, and stop orders.

#### Key Classes/Functions
- `OrderBook.check_triggers()` -- stop order trigger logic (lines 750-782)
- `OrderBook.amend_order()` -- order amendment API (lines 832-890)
- `SimulatorExchangeState.__post_init__()` -- late-load of fee defaults from config (line 609)

#### Bugs and Issues

- **[BUG-SIM-001] Severity: LOW** -- `OrderBook.check_triggers()` uses `direction = order.trigger_direction or TriggerDirection.RISES_TO` (line 773). A stop order with `trigger_direction=None` is a configuration error but is silently treated as RISES_TO.
  - Root cause: Defensive default hides improperly constructed stop orders.
  - Impact: Misconfigured stop orders behave as RISES_TO rather than raising.
  - Suggested fix: Raise `ValueError` if `order.is_conditional` and `trigger_direction is None`.

- **[BUG-SIM-002] Severity: LOW** -- `OrderBook.add_order()` mutates `order.order_id` when the ID is empty (line 708). The condition `if not order.order_id:` treats any falsy string (including `"0"`) as empty, creating dual ID-assignment paths.
  - Impact: Minor in practice; only the exchange pre-assigns IDs via the submit methods.

#### Code Quality Notes
- `LedgerConfig.__post_init__` uses `object.__setattr__(self, ...)` on a non-frozen dataclass (line 53 in ledger.py). Only needed for frozen dataclasses.

---

### exchange.py (~1415 lines)

#### Summary
Main exchange orchestrator. Despite the docstring target of ~200 LOC, the actual file is ~1415 lines. Major sub-steps have helpers, but \, \, \, and \ make this the heaviest file in the domain.

#### Key Classes/Functions
- \ -- main simulation step (lines 710-806)
- \ -- 1m-granular or OHLC TP/SL check (lines 579-642)
- \ -- equity vs. maintenance margin check (lines 654-704)
- \ -- position close and trade record creation (lines 1023-1132)
- \ -- trailing stop update logic (lines 1272-1352)

#### Bugs and Issues

- **[BUG-SIM-003] Severity: MED** -- Liquidation fee is double-counted in the ledger. In \ (lines 695-702):
  1. \ calls \ where \ already contains the liquidation fee from \.
  2. Then \ is called on line 702, deducting the same fee a second time.
  - Root cause: \ passes the fill fee to \, then the caller also applies it via \.
  - Impact: Every liquidation deducts the liquidation fee twice from cash balance. Equity is understated after every liquidation.
  - Suggested fix: Set \ in the liquidation fill in \ and keep the explicit \ call, OR remove the \ call and rely on \.

- **[BUG-SIM-004] Severity: MED** -- \ uses \ (lines 1048-1053). The strings \ and \ are NOT in \ and fall through to \.
  - Root cause: \ is missing entries for forced close types.
  - Impact: Forced closes and end-of-data closes produce fills and trade records tagged as SIGNAL. Metrics are mislabeled.
  - Suggested fix: Add \ and \ to \.

- **[BUG-SIM-005] Severity: LOW** -- Duplicate comment label in \. Both the stop-order section (line 866) and the limit-order section (line 901) are labeled \ The limit section should be 

- **[BUG-SIM-006] Severity: LOW** -- \ increments \ (line 249) before checking if a position or pending market order already exists (lines 257-261). On these silent reject paths, neither \ nor \ is updated, making starvation metrics slightly inaccurate.

- **[FLOW-SIM-001] Severity: MED** -- Trailing stop update (step 4) in \ happens BEFORE the TP/SL check (step 5). A trailing stop adjustment on bar N is immediately evaluated in the same bar's \. On Bybit live, trailing stop updates and TP/SL triggers are asynchronous. The ordering is defensible for conservatism but is not documented as an explicit design decision.

- **[FLOW-SIM-002] Severity: LOW** -- MAE/MFE tracking at step 7 (\) runs AFTER TP/SL exits at step 5. If a TP/SL exit closes the position in this bar, \ is \ at step 7 and tracking is skipped. The closing bar's price range is not captured in MAE.
  - Impact: MAE slightly understated for SL hits.
  - Suggested fix: Move \ to before \.

#### Code Quality Notes
- \ missing return type annotation (line 1220). Should be \.
- \ returns bare \ (line 1029) instead of \. Pyright cannot enforce inner types.
- Comments at lines 757-763 explaining the TP/SL vs signal-close ordering are excellent and should be preserved.

---

### ledger.py (~389 lines)

#### Summary
USDT accounting ledger implementing Bybit isolated margin model. Clean separation of core state and derived values. All mutations call _recompute_derived() to maintain consistency.

#### Key Classes/Functions
- Ledger.update_for_mark_price() -- MTM valuation, IM/MM recalculation (lines 162-216)
- Ledger.apply_exit() / apply_partial_exit() -- PnL realization
- Ledger.compute_required_for_entry() -- entry gate check

#### Bugs and Issues

- **[BUG-SIM-007] Severity: MED** -- After apply_partial_exit() (lines 262-295), _used_margin_usdt and _maintenance_margin_usdt still reflect the pre-close position size. They are only updated on the next update_for_mark_price() call. Between the partial close and that call, available_balance_usdt is understated.
  - Root cause: Intentional design (commented at line 285), but the stale window spans the rest of the same bar processing loop.
  - Impact: If a new entry order is submitted in the same bar after a partial close, the margin check uses stale (larger) used_margin and may incorrectly reject the entry.
  - Suggested fix: After apply_partial_exit, immediately call update_for_mark_price(reduced_position, last_mark_price).

- **[BUG-SIM-008] Severity: LOW** -- LedgerConfig.__post_init__ uses object.__setattr__(self, taker_fee_rate, ...) (line 53) but LedgerConfig is a plain @dataclass (not frozen=True). A normal assignment works here.

#### Code Quality Notes
- Invariant checker check_invariants() with 1e-8 tolerance is good defensive practice.
- IM uses entry price, MM uses mark price. This correctly models Bybit 2025+ isolated margin.

---

### liquidation/liquidation_model.py (~317 lines)

#### Summary
Implements Bybit mark-price triggered liquidation with bankruptcy price settlement. Provides two formula paths: simple bankruptcy price and full cash-balance trigger-form liquidation price.

#### Key Classes/Functions
- calculate_bankruptcy_price() -- staticmethod for BP calculation
- check_liquidation() -- trigger check and event/fill creation
- calculate_liquidation_price() -- full trigger-form liq price (diagnostics)
- estimate_liquidation_price() -- pre-trade estimation without a Position object

#### Bugs and Issues

- **[BUG-SIM-009] Severity: HIGH** -- calculate_bankruptcy_price() is missing the taker fee term. Current implementation (lines 94-97):
  
  Bybit documented bankruptcy price for isolated margin:
  
  - Root cause: Simplified formula omits the fee-to-close term.
  - Impact: Bankruptcy settlement price is slightly more favorable than Bybit (~0.06% difference). Causes systematic discrepancy in liquidation trade PnL.
  - Suggested fix: Add taker_fee_rate parameter to calculate_bankruptcy_price() and apply it.

- **[BUG-SIM-010] Severity: MED** -- Same double-counting as BUG-SIM-003. The liquidation fill (lines 159-170) has fee=liquidation_fee. This fee flows through _close_position() -> apply_exit() AND is applied again by apply_liquidation_fee() in exchange.py line 702.

- **[BUG-SIM-011] Severity: LOW** -- Dead code block at lines 307-313: if mm_deduction > 0 and entry_price > 0: pass. Should be removed.

---

### funding/funding_model.py (~172 lines)

#### Summary
Applies funding rate events to open positions. Bybit-aligned: uses mark price at funding time (not entry price), correct direction for longs (pay positive rates) and shorts (receive).

#### Bugs and Issues

- **[BUG-SIM-012] Severity: MED** -- Time window filtering logic is duplicated. apply_events() filters events internally (lines 93-96) AND filter_events_for_window() (lines 144-170) contains identical logic. The comment "should already be filtered, but double-check" (line 92) signals uncertainty about the interface contract.
  - Impact: If one filtering path is updated, the other may diverge silently.
  - Suggested fix: Establish one authoritative filtering path and document the contract. Either always pre-filter externally and remove in-method filter, or remove filter_events_for_window().

#### Code Quality Notes
- Funding direction is correct: direction = -1.0 for longs on positive rates is Bybit-aligned.

---

### execution/execution_model.py (~672 lines)

#### Summary
Handles all order type execution: market, limit, stop-market, stop-limit. Supports TIF semantics (GTC/IOC/FOK/POST_ONLY). Delegates TP/SL checking to IntrabarPath.

#### Key Classes/Functions
- fill_entry_order() -- market order fill at bar open
- fill_entry_order_1m() -- market order fill using 1m granularity
- check_limit_fill() -- limit order fill condition check
- fill_limit_order() -- limit order execution with TIF handling
- fill_triggered_stop() -- stop order execution after trigger
- fill_exit() -- position close fill
- check_reduce_only() -- reduce-only order size validation

#### Bugs and Issues

- **[BUG-SIM-013] Severity: MED** -- fill_exit() applies market-order slippage to ALL exits unconditionally (lines 551-556). For TP exits where position.tp_order_type == "Limit", the maker fee is correctly used (line 566) but market-order slippage is also applied. Limit TP orders on Bybit fill at the TP price exactly; slippage should be zero.
  - Root cause: Slippage model called unconditionally for all exit types.
  - Impact: Limit TP exits pay both maker fee (correct) and market-order slippage (incorrect), overstating costs.
  - Suggested fix: When reason == FillReason.TAKE_PROFIT and position.tp_order_type == "Limit", set fill_price = exit_price and skip the slippage call.

- **[FLOW-SIM-003] Severity: LOW** -- fill_entry_order_1m() catches (IndexError, AttributeError) at line 212 and silently falls back to exec bar data. This exception handler swallows potential bugs where quote_feed is incorrectly shaped.
  - Suggested fix: Log a warning before falling back.

#### Code Quality Notes
- Fee calculation correctly uses exit notional (fill_size * fill_price, line 560), not entry notional.
- check_reduce_only() correctly clamps size to position size to prevent position flip.

---

### execution/slippage_model.py (~162 lines)

#### Summary
Fixed-bps slippage model. Volume-based mode is planned but unimplemented.

#### Bugs and Issues

- **[BUG-SIM-014] Severity: LOW** -- _calculate_slippage() (lines 134-140): the "volume_based" branch returns the same price * self.slippage_rate as "fixed". Configuring mode: volume_based silently uses fixed slippage.
  - Suggested fix: Raise NotImplementedError for modes other than "fixed".

---

### execution/impact_model.py (~113 lines)

#### Summary
Market impact estimation. Default mode is "disabled". Not used in production.

#### Bugs and Issues

- **[BUG-SIM-015] Severity: LOW** -- get_impact_multiplier() estimates bar USDT volume as bar.volume * bar.close (line 70). For bars with significant intrabar price moves, the close price is a biased estimator. Minor issue as impact is disabled by default.

---

### execution/liquidity_model.py (~120 lines)

#### Summary
Partial fill constraint based on volume fraction. Default mode is "disabled". When enabled, rejects orders exceeding the volume fraction entirely (no partial fills).

#### Bugs and Issues

- **[FLOW-SIM-004] Severity: MED** -- When mode == "volume_fraction" and an order exceeds liquidity, it is rejected entirely. The strategy receives only a LIQUIDITY_EXCEEDED rejection code with no additional notification mechanism.

---

### pricing/price_model.py (~136 lines)

#### Summary
Derives mark/last/mid prices from OHLC bar data. Supports close, hlc3, and ohlc4 mark price sources.

#### Bugs and Issues

- **[BUG-SIM-016] Severity: LOW** -- get_mid_price() accepts a spread parameter (line 84) but ignores it entirely, always returning bar.close. No functional impact since get_prices() correctly derives bid/ask from the returned mid.

---

### pricing/spread_model.py (~110 lines)

#### Summary
Fixed bid-ask spread estimation in bps. Dynamic mode is an unimplemented stub.

#### Bugs and Issues

- **[BUG-SIM-017] Severity: LOW** -- _dynamic_spread() (lines 77-93) returns fixed spread; dynamic mode is unimplemented with no error raised. Configuring mode: dynamic silently uses fixed spread.
  - Suggested fix: Raise NotImplementedError for mode == "dynamic".

---

### pricing/intrabar_path.py (~260 lines)

#### Summary
Two TP/SL checking paths: exec-bar OHLC conservative check and 1m bar chronological scan. The OHLC path uses O->L->H->C ordering to simulate SL-first tie-break conservatively.

#### Key Classes/Functions
- check_tp_sl() -- conservative tie-break within exec bar (SL before TP)
- check_tp_sl_1m() -- chronological scan across 1m bars
- generate_path_for_side() -- side-aware path generation

#### Bugs and Issues

- **[BUG-SIM-018] Severity: MED** -- check_tp_sl_1m() (lines 245-256) performs SL-before-TP checks per 1m bar without position-side-specific intrabar ordering. On Bybit live, within a single 1m bar the tie-break depends on whether price moved high-first or low-first. The 1m check is strictly SL-first regardless of bar direction.
  - Impact: In the edge case where a 1m bar hits both TP and SL (wide range bar), SL always wins. This is conservative (correct project semantics) but is undocumented.

- **[BUG-SIM-019] Severity: LOW** -- generate_path() always uses O -> L -> H -> C ordering (lines 80-85) regardless of position side. External callers using the raw path without check_tp_sl() will see the wrong intrabar order for short positions. Correct API is generate_path_for_side().

---

### metrics/metrics.py (~217 lines)

#### Summary
Exchange-level metrics aggregator. Tracks slippage, fees, funding, liquidations, fills, and rejections. Fully implemented but not wired into the exchange orchestrator.

#### Bugs and Issues

- **[BUG-SIM-020] Severity: MED** -- ExchangeMetrics is instantiated nowhere in exchange.py. SimulatedExchange does not hold an ExchangeMetrics instance and never calls record_step(). The entire metrics module is unused.
  - Root cause: Module built but not connected to the orchestrator.
  - Impact: Exchange-level slippage, fee, and liquidation metrics are never collected during backtests.
  - Suggested fix: Add self._metrics = ExchangeMetrics() to SimulatedExchange.__init__() and call self._metrics.record_step(step_result) at end of process_bar().

---

### constraints/constraints.py (~192 lines)

#### Summary
Tick/lot rounding and min notional validation. Fully implemented but not wired into the execution pipeline.

#### Bugs and Issues

- **[BUG-SIM-021] Severity: MED** -- Constraints is never instantiated or used in exchange.py or execution_model.py. Order constraints (tick size, lot size, min notional) are never applied to orders before execution.
  - Root cause: Module built but not wired into the execution pipeline.
  - Impact: Orders with sub-tick prices or sub-lot quantities are not rounded. Orders below min notional pass through without rejection.
  - Suggested fix: Instantiate Constraints in ExecutionModel or SimulatedExchange and call validate_order() before filling any order.

- **[BUG-SIM-022] Severity: LOW** -- ValidationResult is decorated with @dataclass but also defines an explicit __init__ (lines 50-54). The explicit __init__ overrides the dataclass-generated one, making @dataclass a no-op.
  - Suggested fix: Remove the @dataclass decorator from ValidationResult.

---

## Cross-Module Dependencies



---

## ASCII Diagram



---

## Summary of Findings

### Critical (Must Fix Before Live)

| ID | File:Line | Description |
|----|-----------|-------------|
| BUG-SIM-003/010 | exchange.py:702, liquidation_model.py:159 | Liquidation fee double-counted (deducted via apply_exit AND apply_liquidation_fee) |
| BUG-SIM-009 | liquidation_model.py:94-97 | Bankruptcy price formula missing taker fee term |
| BUG-SIM-004 | exchange.py:1048-1053 | force_close and end_of_data exits tagged as FillReason.SIGNAL |

### Warning (Should Fix)

| ID | File:Line | Description |
|----|-----------|-------------|
| BUG-SIM-007 | ledger.py:285 | Stale margin state after partial close within same bar |
| BUG-SIM-013 | execution_model.py:551-556 | Slippage applied to limit TP exits (should be zero) |
| BUG-SIM-020 | metrics/metrics.py | ExchangeMetrics fully built but not wired into SimulatedExchange |
| BUG-SIM-021 | constraints/constraints.py | Constraints fully built but not wired into execution pipeline |
| BUG-SIM-012 | funding_model.py:92-96,144-170 | Duplicate filtering logic with unclear contract |
| FLOW-SIM-001 | exchange.py:774-777 | Trailing stop update same bar as TP/SL check (undocumented) |
| FLOW-SIM-002 | exchange.py:786 | MAE/MFE misses closing bar (tracking after position cleared) |

### Suggestion (Consider)

| ID | File:Line | Description |
|----|-----------|-------------|
| BUG-SIM-001 | types.py:773 | Silent RISES_TO default for missing trigger_direction |
| BUG-SIM-002 | types.py:706-710 | Dual order ID assignment paths |
| BUG-SIM-008 | ledger.py:53 | object.__setattr__ on non-frozen dataclass |
| BUG-SIM-011 | liquidation_model.py:307-313 | Dead code block for mm_deduction in estimate_liquidation_price |
| BUG-SIM-014 | slippage_model.py:136-138 | volume_based mode silently uses fixed slippage |
| BUG-SIM-017 | spread_model.py:77-93 | dynamic mode unimplemented, no error raised |
| BUG-SIM-022 | constraints.py:50-54 | @dataclass with explicit __init__ -- decorator is no-op |
| FLOW-SIM-003 | execution_model.py:212 | Silent exception swallow in fill_entry_order_1m fallback |
| FLOW-SIM-004 | liquidity_model.py | Liquidity rejection is silent to strategy when mode enabled |
