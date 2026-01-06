# Comprehensive Indicator Test Matrix

**Goal**: Test all 42 indicators across varying timeframes, date ranges, warmup requirements, and MTF configurations to catch edge cases.

## Indicator Registry Summary (42 Total)

### Single-Output Indicators (26)

| # | Indicator | Inputs | Warmup Formula | Default Warmup |
|---|-----------|--------|----------------|----------------|
| 1 | ema | close | 3x length | 60 (len=20) |
| 2 | sma | close | length | 20 |
| 3 | rsi | close | length + 1 | 15 |
| 4 | atr | hlc | length + 1 | 15 |
| 5 | cci | hlc | length | 20 |
| 6 | willr | hlc | length | 14 |
| 7 | roc | close | length | 12 |
| 8 | mom | close | length | 10 |
| 9 | kama | close | 3x length | 30 (len=10) |
| 10 | alma | close | length | 10 |
| 11 | wma | close | length | 9 |
| 12 | dema | close | 3x length | 60 |
| 13 | tema | close | 3x length | 60 |
| 14 | trima | close | length | 10 |
| 15 | zlma | close | 3x length | 60 |
| 16 | natr | hlc | length + 1 | 15 |
| 17 | mfi | hlcv | length | 14 |
| 18 | obv | close,vol | 1 | 1 |
| 19 | cmf | hlcv | length | 20 |
| 20 | cmo | close | length | 14 |
| 21 | linreg | close | length | 14 |
| 22 | midprice | hl | length | 14 |
| 23 | ohlc4 | ohlc | 1 | 1 |
| 24 | trix | close | 3x length | 45 |
| 25 | uo | hlc | max(f,m,s) | 28 |
| 26 | ppo | close | 3x slow + signal | 87 |

### Multi-Output Indicators (16)

| # | Indicator | Inputs | Outputs | Mutually Exclusive | Default Warmup |
|---|-----------|--------|---------|-------------------|----------------|
| 27 | macd | close | macd, signal, histogram | No | 87 |
| 28 | bbands | close | lower, middle, upper, bandwidth, percent_b | No | 20 |
| 29 | stoch | hlc | k, d | No | 20 |
| 30 | stochrsi | close | k, d | No | 34 |
| 31 | adx | hlc | adx, dmp, dmn, adxr | No | 28 |
| 32 | aroon | hl | up, down, osc | No | 26 |
| 33 | kc | hlc | lower, basis, upper | No | 61 |
| 34 | donchian | hl | lower, middle, upper | No | 20 |
| 35 | supertrend | hlc | trend, direction, long, short | **YES** (long/short) | 11 |
| 36 | psar | hlc | long, short, af, reversal | **YES** (long/short) | 2 |
| 37 | squeeze | hlc | sqz, on, off, no_sqz | No | 20 |
| 38 | vortex | hlc | vip, vim | No | 14 |
| 39 | dm | hl | dmp, dmn | No | 14 |
| 40 | fisher | hl | fisher, signal | No | 9 |
| 41 | tsi | close | tsi, signal | No | 51 |
| 42 | kvo | hlcv | kvo, signal | No | 102 |

## Current Coverage Status

| Card | Indicators | TF | Symbol | Status |
|------|------------|-----|--------|--------|
| coverage_01 | rsi, roc, mom, cmo, willr, cci, uo, ppo (8) | 1h | SOLUSDT | Tested |
| coverage_02 | ema, sma, kama, alma, wma, dema, tema, trima, zlma, linreg (10) | 1h | BTCUSDT | Tested |
| coverage_03 | atr, natr, obv, mfi, cmf, midprice, ohlc4, trix (8) | 1h | SOLUSDT | Tested |
| coverage_04 | macd, stoch, stochrsi, tsi, fisher (5) | 1h | BTCUSDT | Tested |
| coverage_05 | adx, aroon, supertrend, vortex, dm, psar (6) | 1h | ETHUSDT | **Fixed** |
| coverage_06 | bbands, kc, donchian, squeeze, kvo (5) | 1h | SOLUSDT | Tested |
| coverage_07 | ema, rsi, atr, macd, adx, supertrend | MTF | SOLUSDT | Tested |

**Total Unique Indicators Covered: 42/42**

## Gap Analysis

### 1. Timeframe Coverage

| TF | Current Coverage | Gap |
|----|------------------|-----|
| 5m | stress05 only | Need more indicators |
| 15m | stress02, stress06, coverage_07 | Partial |
| 1h | All coverage cards | Complete |
| 4h | coverage_07 (htf only) | Need standalone |
| 1D | None | **Missing** |

### 2. Duration Coverage

| Duration | Current | Gap |
|----------|---------|-----|
| 3 days | stress05 | Need more |
| 1 week | stress01 | OK |
| 2 weeks | stress04 | OK |
| 1 month | stress03, stress06 | OK |
| 3 months | None | **Missing** |
| 6 months | stress02 | OK (needs data) |

### 3. Warmup Stress Coverage

| Category | Warmup Bars | Current Test | Gap |
|----------|-------------|--------------|-----|
| Minimal | 1-2 | obv in coverage_03, psar in coverage_05 | OK |
| Low | 10-20 | Many | OK |
| Medium | 50-100 | stress01-07 | OK |
| High | 100-200 | stress04 (700 bars) | OK |
| Extreme | 600+ | stress04 (EMA200=600) | OK |

### 4. Input Requirements Coverage

| Input Type | Indicators | Current Test |
|------------|------------|--------------|
| close only | ema, sma, rsi, roc, mom, kama, alma, wma, dema, tema, trima, zlma, cmo, linreg, trix, ppo, macd, bbands, stochrsi, tsi | All covered |
| high/low | aroon, donchian, dm, fisher, midprice | All covered |
| hlc | atr, cci, willr, natr, uo, stoch, adx, kc, supertrend, psar, squeeze, vortex | All covered |
| hlcv | mfi, cmf, kvo | All covered |
| close+vol | obv | Covered |
| ohlc | ohlc4 | Covered |

### 5. Mutually Exclusive Output Coverage

| Indicator | Exclusive Outputs | Status |
|-----------|-------------------|--------|
| supertrend | long/short | **Fixed** - excluded from required_indicators |
| psar | long/short | **Fixed** - excluded from required_indicators |

### 6. MTF Configuration Coverage

| Config | Current Test | Gap |
|--------|--------------|-----|
| Single-TF | All coverage cards | OK |
| 2-TF (exec+htf) | None | **Missing** |
| 3-TF (exec+mtf+htf) | coverage_07, stress02 | OK |

---

## Comprehensive Test Suite Design

### TIER A: Timeframe Matrix Tests (7 cards)

Test all indicators at each timeframe:

| Card | TF | Duration | Indicators | Symbol |
|------|-----|----------|------------|--------|
| tf_matrix_5m | 5m | 3d | all 42 via rotation | SOLUSDT |
| tf_matrix_15m | 15m | 1w | all 42 via rotation | BTCUSDT |
| tf_matrix_1h | 1h | 2w | (existing coverage cards) | various |
| tf_matrix_4h | 4h | 1mo | macd, adx, supertrend, bbands, kc | ETHUSDT |
| tf_matrix_4h_2 | 4h | 1mo | ema, rsi, stoch, aroon, tsi | BTCUSDT |

### TIER B: Duration Edge Cases (5 cards)

| Card | TF | Duration | Target Edge Case |
|------|-----|----------|------------------|
| duration_3day_minimal | 5m | 3d | Minimal viable after warmup |
| duration_1week_high_warmup | 15m | 7d | High warmup + short window |
| duration_3month_standard | 1h | 90d | Memory stress |
| duration_6month_mtf | 15m | 180d | Long duration + MTF |
| duration_year_sparse | 4h | 365d | Ultra-long + sparse trades |

### TIER C: Warmup Stress Tests (5 cards)

| Card | Warmup Bars | Indicators | TF | Duration |
|------|-------------|------------|-----|----------|
| warmup_minimal | 1-5 | obv, ohlc4, psar | 15m | 1w |
| warmup_standard | 20-50 | sma, rsi, atr, bbands | 1h | 2w |
| warmup_high | 80-120 | macd, ppo, kvo, tsi | 1h | 1mo |
| warmup_extreme | 300-600 | ema(200), kama(100), stochrsi | 1h | 2w |
| warmup_mixed | 1-600 | obv + ema(200) together | 1h | 2w |

### TIER D: Volume Indicator Stress (2 cards)

| Card | Indicators | Edge Case |
|------|------------|-----------|
| volume_all | obv, mfi, cmf, kvo | All volume indicators |
| volume_zero_handling | obv, mfi | Zero volume periods (if any) |

### TIER E: MTF Configuration Matrix (3 cards)

| Card | TFs | Indicator Distribution |
|------|-----|----------------------|
| mtf_2tf_exec_htf | 15m + 4h | exec: ema, rsi; htf: macd, adx |
| mtf_3tf_full | 5m + 15m + 1h | exec: ema, rsi; mtf: macd; htf: adx, supertrend |
| mtf_misaligned | 7m + 23m + 3h | Non-standard TFs (if supported) |

### TIER F: Crossover/History Tests (2 cards)

| Card | Feature | Indicators |
|------|---------|------------|
| crossover_single_tf | cross_above/cross_below | ema, macd_histogram |
| crossover_mtf | Cross on htf, trigger on exec | ema (htf), rsi (exec) |

### TIER G: Edge Case Stress Tests (5 cards)

| Card | Edge Case | Test |
|------|-----------|------|
| edge_warmup_equals_window | warmup = available bars | Boundary condition |
| edge_one_bar_after_warmup | warmup + 1 = window | Minimal viable |
| edge_all_mutually_exclusive | supertrend + psar | Both have exclusive outputs |
| edge_max_indicators | 20+ indicators | Column count stress |
| edge_sparse_ohlc4_obv | Instant indicators | 1-bar warmup handling |

---

## Implementation Plan

### Phase 1: Create Missing Test Cards

Priority order:
1. `tf_matrix_5m` - 5m timeframe coverage
2. `tf_matrix_4h` - 4h standalone coverage
3. `mtf_2tf_exec_htf` - 2-TF MTF config
4. `duration_3month_standard` - 3-month duration
5. `warmup_mixed` - Mixed warmup stress

### Phase 2: Update Existing Cards

1. Fix all cards with SuperTrend/PSAR to exclude mutually exclusive outputs
2. Ensure all cards have explicit required_indicators

### Phase 3: Run Full Suite

```bash
# Tier 1: Unit audits (no DB)
python trade_cli.py backtest audit-toolkit
python trade_cli.py backtest audit-rollup
python trade_cli.py backtest metrics-audit
python trade_cli.py backtest metadata-smoke

# Tier 2: YAML normalization
python trade_cli.py backtest play-normalize-batch --dir configs/plays/validation
python trade_cli.py backtest play-normalize-batch --dir configs/plays/stress_test
python trade_cli.py backtest play-normalize-batch --dir configs/plays/comprehensive

# Tier 3: Backtest runs with explicit dates
# (run each card with appropriate date range)

# Tier 4: Parity audits
python trade_cli.py backtest math-parity --play <card>
```

---

## Expected Edge Case Failures

| Card | Expected Failure | Root Cause |
|------|------------------|------------|
| edge_warmup_equals_window | "Insufficient simulation bars" | No bars after warmup |
| mtf_misaligned | "Unknown timeframe" | Non-standard TFs not supported |
| stress08 | "account section is required" | Intentionally broken |
| stress09 | "UNDECLARED_FEATURE" | Intentionally broken |
| stress10 | "not USDT-quoted" | Intentionally broken |

---

## Success Criteria

- [ ] All 42 indicators tested at least once
- [ ] All timeframes (5m, 15m, 1h, 4h) tested
- [ ] All duration ranges (3d to 6mo) tested
- [ ] All warmup categories (1 to 600 bars) tested
- [ ] MTF configurations (1-TF, 2-TF, 3-TF) tested
- [ ] Mutually exclusive outputs handled correctly
- [ ] Volume indicators tested
- [ ] Crossover rules tested
- [ ] No false failures (all expected passes pass)
- [ ] All expected failures fail with correct error messages
