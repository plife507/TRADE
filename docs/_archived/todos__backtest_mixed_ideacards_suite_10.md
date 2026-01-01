# 10 Mixed IdeaCards Backtest Suite

> **Objective**: Create 10 diverse strategy IdeaCards using the **full pandas_ta indicator library** (189 available indicators), then build a sequential smoke suite that runs them one-by-one to expose issues across different indicator combinations.

## Hard Rules (Non-negotiable)

- **TODO-driven work**: All code changes must map to checkboxes below
- **CLI-only validation**: No pytest files - all validation via `trade_cli.py` smoke + backtest subcommands
- **Indicator source**: Use pandas_ta library (189 indicators available, see `reference/pandas_ta/INDICATORS_REFERENCE.md`)
- **Explicit-only**: All indicators must be declared in FeatureSpecs - no implicit defaults

---

## Phase 1: Reference Documentation

### 1.1 Create pandas_ta Indicators Reference
- [x] Create `reference/pandas_ta/INDICATORS_REFERENCE.md` with complete list of 189 available indicators
- [x] Document currently implemented indicators (8: ema, sma, rsi, atr, macd, bbands, stoch, stochrsi)
- [x] Categorize indicators by type (trend, momentum, volatility, volume, etc.)
- [x] Document multi-output indicator expansion rules

### Gate 1 Acceptance
Reference document exists and lists all 189 pandas_ta indicators with categories.

---

## Phase 2: Make ALL pandas_ta Indicators Available

**Goal**: Clone pandas-ta repo to reference/ and implement dynamic indicator access for ALL 100+ indicators.

### 2.1 Clone pandas-ta Reference Repo
- [x] Clone pandas-ta repo to `reference/pandas_ta_repo/`
- [x] Verify repo structure (momentum/, overlap/, volatility/, volume/, trend/, statistics/, etc.)

### 2.2 Implement Dynamic Indicator System
- [x] Update `IndicatorType` enum with ALL indicators from pandas_ta (150+ indicators)
- [x] Update `MULTI_OUTPUT_KEYS` with all multi-output indicators (ADX, KC, Squeeze, etc.)
- [x] Create dynamic `compute_indicator()` wrapper in `indicator_vendor.py` for all indicators
- [x] Update `IndicatorRegistry.compute()` to use dynamic fallback for all indicators
- [x] Add `_normalize_multi_output()` for consistent column naming
- [ ] Add warmup calculation for new indicators (optional, can use default)

### 2.3 Indicator Categories (from pandas_ta repo)
**Momentum (45 indicators):** ao, apo, bias, bop, brar, cci, cfo, cg, cmo, coppock, cti, dm, er, eri, fisher, inertia, kdj, kst, lrsi, macd, mom, pgo, po, ppo, psl, pvo, qqe, roc, rsi, rsx, rvgi, slope, smi, squeeze, squeeze_pro, stc, stoch, stochrsi, td_seq, trix, trixh, tsi, uo, vwmacd, willr

**Overlap (37 indicators):** alma, dema, ema, fwma, hilo, hl2, hlc3, hma, hwma, ichimoku, jma, kama, linreg, ma, mcgd, midpoint, midprice, mmar, ohlc4, pwma, rainbow, rma, sinwma, sma, ssf, supertrend, swma, t3, tema, trima, vidya, vwap, vwma, wcp, wma, zlma

**Volatility (14 indicators):** aberration, accbands, atr, bbands, donchian, hwc, kc, massi, natr, pdist, rvi, thermo, true_range, ui

**Volume (17 indicators):** ad, adosc, aobv, cmf, efi, eom, kvo, mfi, nvi, obv, pvi, pvol, pvr, pvt, vfi, vp

**Trend (19 indicators):** adx, amat, aroon, chop, cksp, decay, decreasing, dpo, increasing, long_run, pmax, psar, qstick, short_run, tsignals, ttm_trend, vhf, vortex, xsignals

**Statistics (10 indicators):** entropy, kurtosis, mad, median, quantile, skew, stdev, tos_stdevall, variance, zscore

**Performance (3 indicators):** drawdown, log_return, percent_return

**Cycles (2 indicators):** dsp, ebsw

**Candles (5 indicators):** cdl_doji, cdl_inside, cdl_pattern, cdl_z, ha

### Gate 2 Acceptance
- [x] ALL 150 IndicatorType enum values are available
- [x] Dynamic computation via `compute_indicator()` works for any pandas_ta indicator
- [x] `IndicatorRegistry.compute()` dynamically handles ANY indicator from IdeaCard FeatureSpecs
- [x] Verified: EMA, MACD, ADX, KC, CCI, RSI, Supertrend, Williams %R, OBV all work dynamically

---

## Phase 3: Create 10 Mixed IdeaCards

### 3.1 Strategy Categories (Mix Across All 10)

**Trend Following (3 strategies)**
- [ ] `BTCUSDT_1h_ema_trend_pullback_rsi` - EMA structure + RSI pullback entries
- [ ] `SOLUSDT_1h_macd_trend_follow` - MACD trend confirmation
- [ ] `ETHUSDT_4h_sma_trend_follow_macd` - SMA trend + MACD momentum

**Breakout (3 strategies)**
- [ ] `BTCUSDT_1h_bbands_breakout` - Bollinger Bands breakout
- [ ] `SOLUSDT_15m_bbands_breakout` - Fast BBands breakout
- [ ] `ETHUSDT_15m_kc_breakout_short` - Keltner Channel breakout (if implemented) or BBands variant

**Squeeze (2 strategies)**
- [ ] `BTCUSDT_1h_bbands_squeeze_release` - BBands bandwidth squeeze
- [ ] `SOLUSDT_1h_squeeze_pro_release` - Squeeze Pro indicator (if implemented) or BBands variant

**Pullbacks / Mean Reversion (2 strategies)**
- [ ] `ETHUSDT_1h_stoch_pullback_in_trend` - Stochastic pullback in uptrend
- [ ] `BTCUSDT_1h_stochrsi_momentum_pullback` - StochRSI momentum pullback

### 3.2 IdeaCard Requirements (All Must Have)
- [ ] Explicit `account` section (starting_equity_usdt, max_leverage, fee_model, slippage_bps)
- [ ] `symbol_universe` with USDT pairs (mix: BTCUSDT, SOLUSDT, ETHUSDT)
- [ ] `tf_configs` with exec (required), optional htf/mtf
- [ ] `feature_specs` with explicit indicator declarations
- [ ] `required_indicators` matching feature_specs output_keys
- [ ] `signal_rules` with entry_rules and exit_rules
- [ ] `risk_model` with stop_loss, take_profit, sizing
- [ ] `position_policy` (long_only, short_only, or long_short)
- [ ] `bars_history_required` if needed for lookback

### 3.3 Indicator Randomization Strategy
- [ ] Use mix of currently implemented (8) + newly added (2-3) indicators
- [ ] Each IdeaCard uses 2-4 indicators minimum
- [ ] Mix single-output and multi-output indicators
- [ ] Use HTF/MTF filters where appropriate (trend bias, momentum confirmation)
- [ ] Document which indicators are used in each IdeaCard

### Gate 3 Acceptance
10 IdeaCard YAML files exist in `configs/idea_cards/` and all validate via `backtest preflight`.

---

## Phase 4: Suite Configuration

### 4.1 Create Suite Config YAML
- [ ] Create `configs/backtest_suites/mixed_idea_cards_10.yml`
- [ ] Define ordered list of 10 `idea_card_id`s
- [ ] Define per-case preflight windows:
  - Multi-year: `2024-01-01 → 2025-12-14` (default for most)
  - Some shorter windows: `2024-06-01 → 2025-12-14`, `2024-09-01 → 2025-12-14`
- [ ] Define shared compute window for indicator discovery: `2025-10-01 → 2025-12-14` (last ~75 days)

### Gate 4 Acceptance
Suite config YAML exists and lists all 10 IdeaCards with window configurations.

---

## Phase 5: Sequential Suite Runner

### 5.1 Add Suite Runner Function
- [ ] Add `run_backtest_suite(suite_config_path, data_env="live")` to `src/cli/smoke_tests.py`
- [ ] Load suite YAML config
- [ ] For each IdeaCard in sequence:
  1. **Indicator Discovery**: `backtest_indicators_tool(..., compute_values=True, start=compute_start, end=compute_end)`
  2. **Preflight**: `backtest_preflight_idea_card_tool(..., start=preflight_start, end=preflight_end)`
  3. **Smoke Run**: `backtest_run_idea_card_tool(..., smoke=True)` (uses last 100 bars, fast wiring check)
- [ ] Continue after failures (don't stop on first error)
- [ ] Print per-case diagnostics (which step failed, actionable fix commands)

### 5.2 Output Format
- [ ] Print suite header with total cases
- [ ] For each case: print IdeaCard ID, symbol, exec TF, indicator keys
- [ ] Print pass/fail status per step (indicators/preflight/smoke)
- [ ] Print summary at end: total passed/failed
- [ ] Print actionable diagnostics for failures (e.g., "Run: `backtest data-fix --idea-card X`")

### Gate 5 Acceptance
Suite runner executes all 10 cases sequentially and prints clear diagnostics.

---

## Phase 6: CLI Integration

### 6.1 Add CLI Flag
- [ ] Update `trade_cli.py` argparse to add `--backtest-suite` flag for `--smoke backtest`
- [ ] Add optional `--backtest-suite-path` to override default suite YAML
- [ ] Behavior:
  - `python trade_cli.py --smoke backtest` (unchanged): runs single IdeaCard smoke (current behavior)
  - `python trade_cli.py --smoke backtest --backtest-suite`: runs 10-case sequential suite

### Gate 6 Acceptance
CLI flag works and triggers suite runner without breaking existing single-card smoke.

---

## Acceptance Criteria (Done Definition)

- [x] Reference document exists with all 189 pandas_ta indicators listed
- [ ] 10 IdeaCard YAMLs exist and validate via `backtest preflight`
- [ ] Suite config YAML exists with all cases + windows
- [ ] `python trade_cli.py --smoke backtest --backtest-suite` runs all 10 cases sequentially
- [ ] Output clearly distinguishes coverage vs indicator-key vs runtime issues
- [ ] Failures print actionable fix commands (e.g., `backtest data-fix`, `backtest indicators --print-keys`)

---

## Files to Create/Modify

### New Files
- [x] `reference/pandas_ta/INDICATORS_REFERENCE.md` - Complete indicator reference
- [ ] `configs/backtest_suites/mixed_idea_cards_10.yml` - Suite configuration
- [ ] 10 IdeaCard YAMLs in `configs/idea_cards/`:
  - `BTCUSDT_1h_ema_trend_pullback_rsi.yml`
  - `SOLUSDT_1h_macd_trend_follow.yml`
  - `ETHUSDT_4h_sma_trend_follow_macd.yml`
  - `BTCUSDT_1h_bbands_breakout.yml`
  - `SOLUSDT_15m_bbands_breakout.yml`
  - `ETHUSDT_15m_kc_breakout_short.yml` (or BBands variant)
  - `BTCUSDT_1h_bbands_squeeze_release.yml`
  - `SOLUSDT_1h_squeeze_pro_release.yml` (or BBands variant)
  - `ETHUSDT_1h_stoch_pullback_in_trend.yml`
  - `BTCUSDT_1h_stochrsi_momentum_pullback.yml`

### Modified Files
- [ ] `src/backtest/features/feature_spec.py` - Add new IndicatorType enum values (if adding indicators)
- [ ] `src/backtest/indicator_vendor.py` - Add wrapper functions for new indicators (if adding)
- [ ] `src/cli/smoke_tests.py` - Add `run_backtest_suite()` function
- [ ] `trade_cli.py` - Add `--backtest-suite` flag

---

## Known Constraints

- **Indicator availability**: Only 8 indicators currently have wrapper functions. To use others, must add wrappers first (Phase 2).
- **Data coverage**: Suite assumes data exists for BTCUSDT, SOLUSDT, ETHUSDT from 2024-01-01 to 2025-12-14. If missing, suite will fail with actionable data-fix commands.
- **Multi-output naming**: Must use correct expanded keys (e.g., `macd_macd`, `bbands_percent_b`) in signal_rules.

---

## Next Steps After Completion

1. Run full suite: `python trade_cli.py --smoke backtest --backtest-suite`
2. Review failures and fix data/indicator issues
3. Expand indicator implementation based on suite results
4. Add more IdeaCards using newly implemented indicators

