# Codebase Review

Last reviewed: 2026-02-17
Next review: pending

## How to Run a Review

1. Run validation: `python trade_cli.py validate quick`
2. Run type check: `pyright`
3. Review `src/` packages for new findings
4. Add findings below with severity, file, and fix plan
5. Track fixes in `docs/TODO.md` under "Open Bugs & Architecture Gaps"

## Findings

### ~~Backtest does not hard-fail on max drawdown / liquidation~~ FIXED (2026-02-17)

- **Severity**: CRITICAL (safety + CI signal correctness)
- **Status**: **FIXED** — GAP-3, GAP-4, GAP-5 all closed.
- **User expectation**: If **max drawdown is hit** or **liquidation occurs**, the backtest should **FAIL** and the CLI should **exit non-zero**.

#### What’s working well

- **Engine-level max drawdown enforcement is implemented and deterministic**.
  - `PlayEngine.process_bar()` tracks a peak-equity high-water mark and, if breached, returns early (skipping signal generation).
  - Ref: `src/engine/play_engine.py:452-465`

- **Live runner halts “for real” using global panic**.
  - `LiveRunner._check_max_drawdown()` triggers `PanicState` and stops the live loop via `_stop_event.set()`.
  - Ref: `src/engine/runners/live_runner.py:1069-1115`
  - Panic loop halt check: `src/core/safety.py:335-348`

#### Key inconsistencies / gaps (why backtests still “pass”)

1) **Max drawdown stops the backtest loop, but the stop status is not surfaced to the pipeline**

- `BacktestRunner.run()` breaks early when drawdown exceeds `max_drawdown_pct` (good).
  - Ref: `src/engine/runners/backtest_runner.py:402-416`
- But stop details are stored only inside `BacktestResult.metadata` (not first-class fields).
  - Ref: `src/engine/runners/backtest_runner.py:768-776`
- Then `run_engine_with_play()` converts `BacktestResult` → `PlayBacktestResult` and **drops** the stop fields (sets `None`/`False`).
  - Ref: `src/backtest/engine_factory.py:480-493`

**Impact**: The unified backtest pipeline cannot “see” max drawdown stops, so it cannot fail the run based on them.

2) **Liquidation exists in the simulator but is not treated as a terminal stop**

- `SimulatedExchange.process_bar()` checks liquidation and closes the position with reason `"liquidation"`.
  - Ref: `src/backtest/sim/exchange.py:651-687`
- `StopReason` already documents liquidation/max-drawdown as terminal stop taxonomy, but it is not enforced by the runner pipeline today.
  - Ref: `src/backtest/types.py:28-51`

**Impact**: Liquidations can occur and the backtest pipeline still returns success.

3) **Unified backtest runner marks success based on gates/artifacts, not terminal risk events**

- `run_backtest_with_gates()` sets `result.success = True` after completing gates and exporting artifacts, with no explicit check for terminal stop conditions.
  - Ref: `src/backtest/runner.py:959-985`

**Impact**: CLI can exit 0 even when trading safety rules were violated during the run.

#### Defaults + units note (drawdown config)

- `defaults.yml` stores `max_drawdown_pct` as a decimal (`0.20`) and `AccountConfig.from_dict()` converts it to percent as needed.
  - Ref: `config/defaults.yml:50-54`
  - Ref: `src/backtest/play/config_models.py:168-176`

#### Recommended fix direction (spec-level)

- **Propagate stop status** from `BacktestRunner` → `PlayBacktestResult` (do not discard it in `engine_factory.run_engine_with_play()`).
- Add a **terminal risk-stop gate** in `run_backtest_with_gates()` to fail the run when:
  - max drawdown stop occurred, or
  - liquidation occurred (e.g., any trade has `exit_reason == "liquidation"`), or
  - any other terminal stop taxonomy (e.g., equity floor) is triggered.

Once `ToolResult.success` becomes false, `trade_cli.py backtest run ...` will already exit non-zero via `handle_backtest_run()` returning `0 if result.success else 1`.
