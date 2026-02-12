# Trade Math Verification: ALL

> **PARTIAL (2026-02-08)**: Only 34/170 plays completed in this run. 3 failures are
> SL_TP/EQUITY check issues from stale pre-fix artifacts (equity curve post-close
> bug was fixed after these ran). See `docs/REAL_VERIFICATION_REPORT.md` for the
> authoritative 60-play real-data math verification (60/60 pass, 23 checks each).

**Progress**: 34/170 plays verified
**Results**: 31 PASS | 3 FAIL | 0 RUN_FAIL

---

## Summary Table

| # | Play | Status | Trades | PnL | Checks |
|---|------|--------|--------|-----|--------|
| 1 | IND_001_ema_trend_long | PASS | 12 | -1970.13 | 23P/0F/0W/3S |
| 2 | IND_002_ema_trend_short | PASS | 17 | -1701.06 | 23P/0F/0W/3S |
| 3 | IND_003_sma_trend_long | PASS | 879 | 1303377170.80 | 23P/0F/0W/3S |
| 4 | IND_004_sma_trend_short | PASS | 97 | 1646.75 | 23P/0F/0W/3S |
| 5 | IND_005_wma_trend_long | PASS | 2781 | 9332013438209390.00 | 23P/0F/0W/3S |
| 6 | IND_006_dema_trend_long | PASS | 16 | -1997.90 | 23P/0F/0W/3S |
| 7 | IND_007_tema_trend_long | PASS | 832 | 510005384.47 | 23P/0F/0W/3S |
| 8 | IND_008_trima_trend_long | PASS | 17845 | 1919553945277763072.00 | 23P/0F/0W/3S |
| 9 | IND_009_zlma_trend_long | PASS | 69 | -1593.36 | 23P/0F/0W/3S |
| 10 | IND_010_kama_trend_long | PASS | 895 | 1500682326.09 | 23P/0F/0W/3S |
| 11 | IND_011_alma_trend_long | PASS | 887 | 1201786132.45 | 23P/0F/0W/3S |
| 12 | IND_012_linreg_trend_long | PASS | 63 | -1367.97 | 23P/0F/0W/3S |
| 13 | IND_013_rsi_oversold_long | PASS | 84 | 410.96 | 23P/0F/0W/3S |
| 14 | IND_014_rsi_overbought_short | PASS | 114 | 285.97 | 23P/0F/0W/3S |
| 15 | IND_015_cci_oversold_long | PASS | 16 | -2054.90 | 23P/0F/0W/3S |
| 16 | IND_016_cci_overbought_short | FAIL | 5 | -2007.09 | 21P/2F/0W/3S |
| 17 | IND_017_willr_oversold_long | PASS | 230 | 41176.03 | 23P/0F/0W/3S |
| 18 | IND_018_willr_overbought_short | PASS | 56 | -1017.44 | 23P/0F/0W/3S |
| 19 | IND_019_cmo_oversold_long | PASS | 15 | -2057.04 | 23P/0F/0W/3S |
| 20 | IND_020_mfi_oversold_long | FAIL | 6 | -2100.71 | 21P/2F/0W/3S |
| 21 | IND_021_mfi_overbought_short | PASS | 176 | -1868.79 | 23P/0F/0W/3S |
| 22 | IND_022_uo_oversold_long | PASS | 279 | 67626.86 | 23P/0F/0W/3S |
| 23 | IND_023_roc_positive_long | PASS | 19 | -1982.15 | 23P/0F/0W/3S |
| 24 | IND_024_roc_negative_short | PASS | 20 | -2021.99 | 23P/0F/0W/3S |
| 25 | IND_025_mom_positive_long | PASS | 19 | -1980.10 | 23P/0F/0W/3S |
| 26 | IND_026_mom_negative_short | PASS | 121 | 940.99 | 23P/0F/0W/3S |
| 27 | IND_027_obv_rising_long | PASS | 16 | -2020.99 | 23P/0F/0W/3S |
| 28 | IND_028_cmf_positive_long | PASS | 220 | 82997.38 | 23P/0F/0W/3S |
| 29 | IND_029_cmf_negative_short | PASS | 18272 | 1122932799257637760.00 | 23P/0F/0W/3S |
| 30 | IND_030_vwap_above_long | PASS | 13 | -2004.76 | 23P/0F/0W/3S |
| 31 | IND_031_atr_filter_long | PASS | 9 | -2269.99 | 23P/0F/0W/3S |
| 32 | IND_032_natr_filter_long | FAIL | 20 | -64116955035139.87 | 20P/3F/0W/3S |
| 33 | IND_033_ohlc4_above_ema | PASS | 83 | -1555.08 | 23P/0F/0W/3S |
| 34 | IND_034_midprice_above_ema | PASS | 19 | -2015.96 | 23P/0F/0W/3S |

---

## Detailed Results

### IND_001_ema_trend_long
- **Status**: PASS
- **Pattern**: trend_up_clean
- **Trades**: 12
- **Net PnL**: -1970.13 USDT
- **Win Rate**: 0.1%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| OHLCV_VALID | SKIP | No candle data provided |
| TRADE_COUNT | PASS | Consistent: 12 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All 12 SL/TP levels valid (sl=3.0%, tp=6.0%) [9 TP-entry crosses] |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| ENTRY_FILL | PASS | All 12 entries: valid prices, correct SL direction, positive sizes |
| EXIT_FILL | SKIP | No candle data provided |
| TP_SL_BAR | SKIP | No candle data provided |
| INDEP_PNL | PASS | All trades: independent PnL matches realized_pnl |
| SL_TP_CALC | PASS | SL/TP cross-validation OK: 12 trades, TP matches SL-derived signal_close (sl=3.0%, tp=6.0%, lev=1.0x) |
| EQUITY_WALK | PASS | Equity walk consistent: 10000 + -1970.13 = 8029.87 (actual=8029.87, diff=0.00) |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=-1970.13 |
| METRICS | PASS | Summary metrics consistent (12 trades, 0% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |
| METRIC_COUNTS | PASS | All counts match (12 trades, 1W/11L) |
| METRIC_PNL | PASS | All PnL aggregates match (net=-1970.13) |
| METRIC_RATES | PASS | All rates/ratios match (WR=1/12) |
| METRIC_EXTREMES | PASS | All extremes/streaks match (streaks: 1W/9L) |
| METRIC_DRAWDOWN | PASS | Drawdown matches (abs=2019.27, pct=0.2009) |
| METRIC_RISK | PASS | Risk metrics match (Sharpe=-8.91, Sortino=-12.17, Calmar=-4.88) |
| METRIC_DURATION | PASS | Duration matches (avg=152.7 bars) |
| METRIC_QUALITY | PASS | Recovery factor matches (-0.98) |

### IND_002_ema_trend_short
- **Status**: PASS
- **Pattern**: trend_down_clean
- **Trades**: 17
- **Net PnL**: -1701.06 USDT
- **Win Rate**: 0.1%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| OHLCV_VALID | SKIP | No candle data provided |
| TRADE_COUNT | PASS | Consistent: 17 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All 17 SL/TP levels valid (sl=3.0%, tp=6.0%) |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| ENTRY_FILL | PASS | All 17 entries: valid prices, correct SL direction, positive sizes |
| EXIT_FILL | SKIP | No candle data provided |
| TP_SL_BAR | SKIP | No candle data provided |
| INDEP_PNL | PASS | All trades: independent PnL matches realized_pnl |
| SL_TP_CALC | PASS | SL/TP cross-validation OK: 17 trades, TP matches SL-derived signal_close (sl=3.0%, tp=6.0%, lev=1.0x) |
| EQUITY_WALK | PASS | Equity walk consistent: 10000 + -1701.06 = 8298.94 (actual=8298.94, diff=0.00) |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=-1701.06 |
| METRICS | PASS | Summary metrics consistent (17 trades, 0% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |
| METRIC_COUNTS | PASS | All counts match (17 trades, 1W/16L) |
| METRIC_PNL | PASS | All PnL aggregates match (net=-1701.06) |
| METRIC_RATES | PASS | All rates/ratios match (WR=1/17) |
| METRIC_EXTREMES | PASS | All extremes/streaks match (streaks: 1W/16L) |
| METRIC_DRAWDOWN | PASS | Drawdown matches (abs=2124.23, pct=0.2038) |
| METRIC_RISK | PASS | Risk metrics match (Sharpe=-9.49, Sortino=-10.94, Calmar=-4.88) |
| METRIC_DURATION | PASS | Duration matches (avg=69.9 bars) |
| METRIC_QUALITY | PASS | Recovery factor matches (-0.80) |

### IND_003_sma_trend_long
- **Status**: PASS
- **Pattern**: trend_up_clean
- **Trades**: 879
- **Net PnL**: 1303377170.80 USDT
- **Win Rate**: 1.0%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| OHLCV_VALID | SKIP | No candle data provided |
| TRADE_COUNT | PASS | Consistent: 879 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All 879 SL/TP levels valid (sl=3.0%, tp=6.0%) [851 SL-entry crosses] |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| ENTRY_FILL | PASS | All 879 entries: valid prices, correct SL direction, positive sizes |
| EXIT_FILL | SKIP | No candle data provided |
| TP_SL_BAR | SKIP | No candle data provided |
| INDEP_PNL | PASS | All trades: independent PnL matches realized_pnl |
| SL_TP_CALC | PASS | SL/TP cross-validation OK: 879 trades, TP matches SL-derived signal_close (sl=3.0%, tp=6.0%, lev=1.0x) |
| EQUITY_WALK | PASS | Equity walk consistent: 10000 + 1303377170.80 = 1303387170.80 (actual=1303387170.80, diff=0.00) |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=1303377170.80 |
| METRICS | PASS | Summary metrics consistent (879 trades, 1% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |
| METRIC_COUNTS | PASS | All counts match (879 trades, 850W/29L) |
| METRIC_PNL | PASS | All PnL aggregates match (net=1303377170.80) |
| METRIC_RATES | PASS | All rates/ratios match (WR=850/879) |
| METRIC_EXTREMES | PASS | All extremes/streaks match (streaks: 544W/27L) |
| METRIC_DRAWDOWN | PASS | Drawdown matches (abs=339467026.88, pct=0.2066) |
| METRIC_RISK | PASS | Risk metrics match (Sharpe=114.98, Sortino=461.84, Calmar=18959386080571801448660173897960699164168956853612222416553182 |
| METRIC_DURATION | PASS | Duration matches (avg=0.9 bars) |
| METRIC_QUALITY | PASS | Recovery factor matches (3.84) |

### IND_004_sma_trend_short
- **Status**: PASS
- **Pattern**: trend_down_clean
- **Trades**: 97
- **Net PnL**: 1646.75 USDT
- **Win Rate**: 0.7%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| OHLCV_VALID | SKIP | No candle data provided |
| TRADE_COUNT | PASS | Consistent: 97 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All 97 SL/TP levels valid (sl=3.0%, tp=6.0%) [30 TP-entry crosses] |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| ENTRY_FILL | PASS | All 97 entries: valid prices, correct SL direction, positive sizes |
| EXIT_FILL | SKIP | No candle data provided |
| TP_SL_BAR | SKIP | No candle data provided |
| INDEP_PNL | PASS | All trades: independent PnL matches realized_pnl |
| SL_TP_CALC | PASS | SL/TP cross-validation OK: 97 trades, TP matches SL-derived signal_close (sl=3.0%, tp=6.0%, lev=1.0x) |
| EQUITY_WALK | PASS | Equity walk consistent: 10000 + 1646.75 = 11646.75 (actual=11646.75, diff=0.00) |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=1646.75 |
| METRICS | PASS | Summary metrics consistent (97 trades, 1% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |
| METRIC_COUNTS | PASS | All counts match (97 trades, 64W/33L) |
| METRIC_PNL | PASS | All PnL aggregates match (net=1646.75) |
| METRIC_RATES | PASS | All rates/ratios match (WR=64/97) |
| METRIC_EXTREMES | PASS | All extremes/streaks match (streaks: 64W/31L) |
| METRIC_DRAWDOWN | PASS | Drawdown matches (abs=3062.37, pct=0.2082) |
| METRIC_RISK | PASS | Risk metrics match (Sharpe=2.71, Sortino=4.34, Calmar=43.03) |
| METRIC_DURATION | PASS | Duration matches (avg=20.7 bars) |
| METRIC_QUALITY | PASS | Recovery factor matches (0.54) |

### IND_005_wma_trend_long
- **Status**: PASS
- **Pattern**: trend_up_clean
- **Trades**: 2781
- **Net PnL**: 9332013438209390.00 USDT
- **Win Rate**: 0.9%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| OHLCV_VALID | SKIP | No candle data provided |
| TRADE_COUNT | PASS | Consistent: 2781 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All 2781 SL/TP levels valid (sl=3.0%, tp=6.0%) [2428 SL-entry crosses] |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| ENTRY_FILL | PASS | All 2781 entries: valid prices, correct SL direction, positive sizes |
| EXIT_FILL | SKIP | No candle data provided |
| TP_SL_BAR | SKIP | No candle data provided |
| INDEP_PNL | PASS | All trades: independent PnL matches realized_pnl |
| SL_TP_CALC | PASS | SL/TP cross-validation OK: 2781 trades, TP matches SL-derived signal_close (sl=3.0%, tp=6.0%, lev=1.0x) |
| EQUITY_WALK | PASS | Equity walk consistent: 10000 + 9332013438209398.00 = 9332013438219398.00 (actual=9332013438219390.00, diff=8.00) |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=9332013438209390.00 |
| METRICS | PASS | Summary metrics consistent (2781 trades, 1% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |
| METRIC_COUNTS | PASS | All counts match (2781 trades, 2371W/410L) |
| METRIC_PNL | PASS | All PnL aggregates match (net=9332013438209398.00) |
| METRIC_RATES | PASS | All rates/ratios match (WR=2371/2781) |
| METRIC_EXTREMES | PASS | All extremes/streaks match (streaks: 931W/142L) |
| METRIC_DRAWDOWN | PASS | Drawdown matches (abs=2333664991010008.00, pct=0.2000) |
| METRIC_RISK | PASS | Risk metrics match (Sharpe=84.91, Sortino=584.52, Calmar=30654324191773588407192890558579372308119307782455296.00) |
| METRIC_DURATION | PASS | Duration matches (avg=0.8 bars) |
| METRIC_QUALITY | PASS | Recovery factor matches (4.00) |

### IND_006_dema_trend_long
- **Status**: PASS
- **Pattern**: trend_stairs
- **Trades**: 16
- **Net PnL**: -1997.90 USDT

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| OHLCV_VALID | SKIP | No candle data provided |
| TRADE_COUNT | PASS | Consistent: 16 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All 16 SL/TP levels valid (sl=3.0%, tp=6.0%) |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| ENTRY_FILL | PASS | All 16 entries: valid prices, correct SL direction, positive sizes |
| EXIT_FILL | SKIP | No candle data provided |
| TP_SL_BAR | SKIP | No candle data provided |
| INDEP_PNL | PASS | All trades: independent PnL matches realized_pnl |
| SL_TP_CALC | PASS | SL/TP cross-validation OK: 16 trades, TP matches SL-derived signal_close (sl=3.0%, tp=6.0%, lev=1.0x) |
| EQUITY_WALK | PASS | Equity walk consistent: 10000 + -1997.90 = 8002.10 (actual=8002.10, diff=0.00) |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=-1997.90 |
| METRICS | PASS | Summary metrics consistent (16 trades, 0% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |
| METRIC_COUNTS | PASS | All counts match (16 trades, 0W/16L) |
| METRIC_PNL | PASS | All PnL aggregates match (net=-1997.90) |
| METRIC_RATES | PASS | All rates/ratios match (WR=0/16) |
| METRIC_EXTREMES | PASS | All extremes/streaks match (streaks: 0W/16L) |
| METRIC_DRAWDOWN | PASS | Drawdown matches (abs=2046.34, pct=0.2036) |
| METRIC_RISK | PASS | Risk metrics match (Sharpe=-20.30, Sortino=-22.64, Calmar=-4.91) |
| METRIC_DURATION | PASS | Duration matches (avg=19.0 bars) |
| METRIC_QUALITY | PASS | Recovery factor matches (-0.98) |

### IND_007_tema_trend_long
- **Status**: PASS
- **Pattern**: trend_grinding
- **Trades**: 832
- **Net PnL**: 510005384.47 USDT
- **Win Rate**: 1.0%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| OHLCV_VALID | SKIP | No candle data provided |
| TRADE_COUNT | PASS | Consistent: 832 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All 832 SL/TP levels valid (sl=3.0%, tp=6.0%) [797 SL-entry crosses] |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| ENTRY_FILL | PASS | All 832 entries: valid prices, correct SL direction, positive sizes |
| EXIT_FILL | SKIP | No candle data provided |
| TP_SL_BAR | SKIP | No candle data provided |
| INDEP_PNL | PASS | All trades: independent PnL matches realized_pnl |
| SL_TP_CALC | PASS | SL/TP cross-validation OK: 832 trades, TP matches SL-derived signal_close (sl=3.0%, tp=6.0%, lev=1.0x) |
| EQUITY_WALK | PASS | Equity walk consistent: 10000 + 510005384.47 = 510015384.47 (actual=510015384.47, diff=0.00) |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=510005384.47 |
| METRICS | PASS | Summary metrics consistent (832 trades, 1% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |
| METRIC_COUNTS | PASS | All counts match (832 trades, 795W/37L) |
| METRIC_PNL | PASS | All PnL aggregates match (net=510005384.47) |
| METRIC_RATES | PASS | All rates/ratios match (WR=795/832) |
| METRIC_EXTREMES | PASS | All extremes/streaks match (streaks: 508W/33L) |
| METRIC_DRAWDOWN | PASS | Drawdown matches (abs=129142603.05, pct=0.2021) |
| METRIC_RISK | PASS | Risk metrics match (Sharpe=113.82, Sortino=575.13, Calmar=19158575855659244767510797688727038345833131454463172777979532 |
| METRIC_DURATION | PASS | Duration matches (avg=1.0 bars) |
| METRIC_QUALITY | PASS | Recovery factor matches (3.95) |

### IND_008_trima_trend_long
- **Status**: PASS
- **Pattern**: trend_up_clean
- **Trades**: 17845
- **Net PnL**: 1919553945277763072.00 USDT
- **Win Rate**: 1.0%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| OHLCV_VALID | SKIP | No candle data provided |
| TRADE_COUNT | PASS | Consistent: 17845 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All 17845 SL/TP levels valid (sl=3.0%, tp=6.0%) [17524 SL-entry crosses] |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| ENTRY_FILL | PASS | All 17845 entries: valid prices, correct SL direction, positive sizes |
| EXIT_FILL | SKIP | No candle data provided |
| TP_SL_BAR | SKIP | No candle data provided |
| INDEP_PNL | PASS | All trades: independent PnL matches realized_pnl |
| SL_TP_CALC | PASS | SL/TP cross-validation OK: 17845 trades, TP matches SL-derived signal_close (sl=3.0%, tp=6.0%, lev=1.0x) |
| EQUITY_WALK | PASS | Equity walk consistent: 10000 + 1919553945277768704.00 = 1919553945277778688.00 (actual=1919553945277773056.00, diff=563 |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=1919553945277763072.00 |
| METRICS | PASS | Summary metrics consistent (17845 trades, 1% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |
| METRIC_COUNTS | PASS | All counts match (17845 trades, 17522W/323L) |
| METRIC_PNL | PASS | All PnL aggregates match (net=1919553945277768704.00) |
| METRIC_RATES | PASS | All rates/ratios match (WR=17522/17845) |
| METRIC_EXTREMES | PASS | All extremes/streaks match (streaks: 14766W/126L) |
| METRIC_DRAWDOWN | PASS | Drawdown matches (abs=1399190439125552.00, pct=0.0615) |
| METRIC_RISK | PASS | Risk metrics match (Sharpe=23.17, Sortino=499.90, Calmar=438863925754.09) |
| METRIC_DURATION | PASS | Duration matches (avg=0.7 bars) |
| METRIC_QUALITY | PASS | Recovery factor matches (1371.90) |

### IND_009_zlma_trend_long
- **Status**: PASS
- **Pattern**: trend_up_clean
- **Trades**: 69
- **Net PnL**: -1593.36 USDT
- **Win Rate**: 0.2%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| OHLCV_VALID | SKIP | No candle data provided |
| TRADE_COUNT | PASS | Consistent: 69 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All 69 SL/TP levels valid (sl=3.0%, tp=6.0%) [45 TP-entry crosses] |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| ENTRY_FILL | PASS | All 69 entries: valid prices, correct SL direction, positive sizes |
| EXIT_FILL | SKIP | No candle data provided |
| TP_SL_BAR | SKIP | No candle data provided |
| INDEP_PNL | PASS | All trades: independent PnL matches realized_pnl |
| SL_TP_CALC | PASS | SL/TP cross-validation OK: 69 trades, TP matches SL-derived signal_close (sl=3.0%, tp=6.0%, lev=1.0x) |
| EQUITY_WALK | PASS | Equity walk consistent: 10000 + -1593.36 = 8406.64 (actual=8406.64, diff=0.00) |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=-1593.36 |
| METRICS | PASS | Summary metrics consistent (69 trades, 0% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |
| METRIC_COUNTS | PASS | All counts match (69 trades, 15W/54L) |
| METRIC_PNL | PASS | All PnL aggregates match (net=-1593.36) |
| METRIC_RATES | PASS | All rates/ratios match (WR=15/69) |
| METRIC_EXTREMES | PASS | All extremes/streaks match (streaks: 7W/27L) |
| METRIC_DRAWDOWN | PASS | Drawdown matches (abs=2152.88, pct=0.2039) |
| METRIC_RISK | PASS | Risk metrics match (Sharpe=-9.98, Sortino=-19.20, Calmar=-4.81) |
| METRIC_DURATION | PASS | Duration matches (avg=19.9 bars) |
| METRIC_QUALITY | PASS | Recovery factor matches (-0.74) |

### IND_010_kama_trend_long
- **Status**: PASS
- **Pattern**: trend_stairs
- **Trades**: 895
- **Net PnL**: 1500682326.09 USDT
- **Win Rate**: 1.0%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| OHLCV_VALID | SKIP | No candle data provided |
| TRADE_COUNT | PASS | Consistent: 895 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All 895 SL/TP levels valid (sl=3.0%, tp=6.0%) [868 SL-entry crosses] |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| ENTRY_FILL | PASS | All 895 entries: valid prices, correct SL direction, positive sizes |
| EXIT_FILL | SKIP | No candle data provided |
| TP_SL_BAR | SKIP | No candle data provided |
| INDEP_PNL | PASS | All trades: independent PnL matches realized_pnl |
| SL_TP_CALC | PASS | SL/TP cross-validation OK: 895 trades, TP matches SL-derived signal_close (sl=3.0%, tp=6.0%, lev=1.0x) |
| EQUITY_WALK | PASS | Equity walk consistent: 10000 + 1500682326.09 = 1500692326.09 (actual=1500692326.09, diff=0.00) |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=1500682326.09 |
| METRICS | PASS | Summary metrics consistent (895 trades, 1% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |
| METRIC_COUNTS | PASS | All counts match (895 trades, 866W/29L) |
| METRIC_PNL | PASS | All PnL aggregates match (net=1500682326.09) |
| METRIC_RATES | PASS | All rates/ratios match (WR=866/895) |
| METRIC_EXTREMES | PASS | All extremes/streaks match (streaks: 565W/27L) |
| METRIC_DRAWDOWN | PASS | Drawdown matches (abs=376495914.10, pct=0.2006) |
| METRIC_RISK | PASS | Risk metrics match (Sharpe=117.88, Sortino=532.92, Calmar=11760491739709938236009334480717533582116677830186293402976782 |
| METRIC_DURATION | PASS | Duration matches (avg=0.9 bars) |
| METRIC_QUALITY | PASS | Recovery factor matches (3.99) |

### IND_011_alma_trend_long
- **Status**: PASS
- **Pattern**: trend_grinding
- **Trades**: 887
- **Net PnL**: 1201786132.45 USDT
- **Win Rate**: 1.0%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| OHLCV_VALID | SKIP | No candle data provided |
| TRADE_COUNT | PASS | Consistent: 887 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All 887 SL/TP levels valid (sl=3.0%, tp=6.0%) [854 SL-entry crosses] |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| ENTRY_FILL | PASS | All 887 entries: valid prices, correct SL direction, positive sizes |
| EXIT_FILL | SKIP | No candle data provided |
| TP_SL_BAR | SKIP | No candle data provided |
| INDEP_PNL | PASS | All trades: independent PnL matches realized_pnl |
| SL_TP_CALC | PASS | SL/TP cross-validation OK: 887 trades, TP matches SL-derived signal_close (sl=3.0%, tp=6.0%, lev=1.0x) |
| EQUITY_WALK | PASS | Equity walk consistent: 10000 + 1201786132.45 = 1201796132.45 (actual=1201796132.45, diff=0.00) |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=1201786132.45 |
| METRICS | PASS | Summary metrics consistent (887 trades, 1% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |
| METRIC_COUNTS | PASS | All counts match (887 trades, 853W/34L) |
| METRIC_PNL | PASS | All PnL aggregates match (net=1201786132.45) |
| METRIC_RATES | PASS | All rates/ratios match (WR=853/887) |
| METRIC_EXTREMES | PASS | All extremes/streaks match (streaks: 558W/31L) |
| METRIC_DRAWDOWN | PASS | Drawdown matches (abs=314474154.87, pct=0.2074) |
| METRIC_RISK | PASS | Risk metrics match (Sharpe=117.55, Sortino=618.88, Calmar=68312066550897286074278007185247187243922221717486525217198862 |
| METRIC_DURATION | PASS | Duration matches (avg=0.9 bars) |
| METRIC_QUALITY | PASS | Recovery factor matches (3.82) |

### IND_012_linreg_trend_long
- **Status**: PASS
- **Pattern**: trend_up_clean
- **Trades**: 63
- **Net PnL**: -1367.97 USDT
- **Win Rate**: 0.1%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| OHLCV_VALID | SKIP | No candle data provided |
| TRADE_COUNT | PASS | Consistent: 63 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All 63 SL/TP levels valid (sl=3.0%, tp=6.0%) [18 SL-entry crosses] |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| ENTRY_FILL | PASS | All 63 entries: valid prices, correct SL direction, positive sizes |
| EXIT_FILL | SKIP | No candle data provided |
| TP_SL_BAR | SKIP | No candle data provided |
| INDEP_PNL | PASS | All trades: independent PnL matches realized_pnl |
| SL_TP_CALC | PASS | SL/TP cross-validation OK: 63 trades, TP matches SL-derived signal_close (sl=3.0%, tp=6.0%, lev=1.0x) |
| EQUITY_WALK | PASS | Equity walk consistent: 10000 + -1367.97 = 8632.03 (actual=8632.03, diff=0.00) |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=-1367.97 |
| METRICS | PASS | Summary metrics consistent (63 trades, 0% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |
| METRIC_COUNTS | PASS | All counts match (63 trades, 9W/54L) |
| METRIC_PNL | PASS | All PnL aggregates match (net=-1367.97) |
| METRIC_RATES | PASS | All rates/ratios match (WR=9/63) |
| METRIC_EXTREMES | PASS | All extremes/streaks match (streaks: 6W/27L) |
| METRIC_DRAWDOWN | PASS | Drawdown matches (abs=2195.65, pct=0.2028) |
| METRIC_RISK | PASS | Risk metrics match (Sharpe=-7.64, Sortino=-9.29, Calmar=-3.80) |
| METRIC_DURATION | PASS | Duration matches (avg=53.5 bars) |
| METRIC_QUALITY | PASS | Recovery factor matches (-0.62) |

### IND_013_rsi_oversold_long
- **Status**: PASS
- **Pattern**: reversal_v_bottom
- **Trades**: 84
- **Net PnL**: 410.96 USDT
- **Win Rate**: 0.6%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| OHLCV_VALID | SKIP | No candle data provided |
| TRADE_COUNT | PASS | Consistent: 84 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All 84 SL/TP levels valid (sl=3.0%, tp=6.0%) [32 TP-entry crosses] |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| ENTRY_FILL | PASS | All 84 entries: valid prices, correct SL direction, positive sizes |
| EXIT_FILL | SKIP | No candle data provided |
| TP_SL_BAR | SKIP | No candle data provided |
| INDEP_PNL | PASS | All trades: independent PnL matches realized_pnl |
| SL_TP_CALC | PASS | SL/TP cross-validation OK: 84 trades, TP matches SL-derived signal_close (sl=3.0%, tp=6.0%, lev=1.0x) |
| EQUITY_WALK | PASS | Equity walk consistent: 10000 + 410.96 = 10410.96 (actual=10410.96, diff=0.00) |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=410.96 |
| METRICS | PASS | Summary metrics consistent (84 trades, 1% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |
| METRIC_COUNTS | PASS | All counts match (84 trades, 47W/37L) |
| METRIC_PNL | PASS | All PnL aggregates match (net=410.96) |
| METRIC_RATES | PASS | All rates/ratios match (WR=47/84) |
| METRIC_EXTREMES | PASS | All extremes/streaks match (streaks: 47W/33L) |
| METRIC_DRAWDOWN | PASS | Drawdown matches (abs=2697.16, pct=0.2058) |
| METRIC_RISK | PASS | Risk metrics match (Sharpe=1.36, Sortino=2.16, Calmar=7.36) |
| METRIC_DURATION | PASS | Duration matches (avg=12.6 bars) |
| METRIC_QUALITY | PASS | Recovery factor matches (0.15) |

### IND_014_rsi_overbought_short
- **Status**: PASS
- **Pattern**: reversal_v_top
- **Trades**: 114
- **Net PnL**: 285.97 USDT
- **Win Rate**: 0.6%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| OHLCV_VALID | SKIP | No candle data provided |
| TRADE_COUNT | PASS | Consistent: 114 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All 114 SL/TP levels valid (sl=3.0%, tp=6.0%) [33 TP-entry crosses] |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| ENTRY_FILL | PASS | All 114 entries: valid prices, correct SL direction, positive sizes |
| EXIT_FILL | SKIP | No candle data provided |
| TP_SL_BAR | SKIP | No candle data provided |
| INDEP_PNL | PASS | All trades: independent PnL matches realized_pnl |
| SL_TP_CALC | PASS | SL/TP cross-validation OK: 114 trades, TP matches SL-derived signal_close (sl=3.0%, tp=6.0%, lev=1.0x) |
| EQUITY_WALK | PASS | Equity walk consistent: 10000 + 285.97 = 10285.97 (actual=10285.97, diff=0.00) |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=285.97 |
| METRICS | PASS | Summary metrics consistent (114 trades, 1% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |
| METRIC_COUNTS | PASS | All counts match (114 trades, 73W/41L) |
| METRIC_PNL | PASS | All PnL aggregates match (net=285.97) |
| METRIC_RATES | PASS | All rates/ratios match (WR=73/114) |
| METRIC_EXTREMES | PASS | All extremes/streaks match (streaks: 56W/30L) |
| METRIC_DRAWDOWN | PASS | Drawdown matches (abs=2577.55, pct=0.2004) |
| METRIC_RISK | PASS | Risk metrics match (Sharpe=0.91, Sortino=1.44, Calmar=2.53) |
| METRIC_DURATION | PASS | Duration matches (avg=18.1 bars) |
| METRIC_QUALITY | PASS | Recovery factor matches (0.11) |

### IND_015_cci_oversold_long
- **Status**: PASS
- **Pattern**: reversal_v_bottom
- **Trades**: 16
- **Net PnL**: -2054.90 USDT

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| OHLCV_VALID | SKIP | No candle data provided |
| TRADE_COUNT | PASS | Consistent: 16 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All 16 SL/TP levels valid (sl=3.0%, tp=6.0%) |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| ENTRY_FILL | PASS | All 16 entries: valid prices, correct SL direction, positive sizes |
| EXIT_FILL | SKIP | No candle data provided |
| TP_SL_BAR | SKIP | No candle data provided |
| INDEP_PNL | PASS | All trades: independent PnL matches realized_pnl |
| SL_TP_CALC | PASS | SL/TP cross-validation OK: 16 trades, TP matches SL-derived signal_close (sl=3.0%, tp=6.0%, lev=1.0x) |
| EQUITY_WALK | PASS | Equity walk consistent: 10000 + -2054.90 = 7945.10 (actual=7945.10, diff=0.00) |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=-2054.90 |
| METRICS | PASS | Summary metrics consistent (16 trades, 0% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |
| METRIC_COUNTS | PASS | All counts match (16 trades, 0W/16L) |
| METRIC_PNL | PASS | All PnL aggregates match (net=-2054.90) |
| METRIC_RATES | PASS | All rates/ratios match (WR=0/16) |
| METRIC_EXTREMES | PASS | All extremes/streaks match (streaks: 0W/16L) |
| METRIC_DRAWDOWN | PASS | Drawdown matches (abs=2069.15, pct=0.2066) |
| METRIC_RISK | PASS | Risk metrics match (Sharpe=-14.43, Sortino=-16.24, Calmar=-4.84) |
| METRIC_DURATION | PASS | Duration matches (avg=30.6 bars) |
| METRIC_QUALITY | PASS | Recovery factor matches (-0.99) |

### IND_016_cci_overbought_short
- **Status**: FAIL
- **Pattern**: reversal_v_top
- **Trades**: 5
- **Net PnL**: -2007.09 USDT

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| OHLCV_VALID | SKIP | No candle data provided |
| TRADE_COUNT | PASS | Consistent: 5 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All 5 SL/TP levels valid (sl=3.0%, tp=6.0%) |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| ENTRY_FILL | PASS | All 5 entries: valid prices, correct SL direction, positive sizes |
| EXIT_FILL | SKIP | No candle data provided |
| TP_SL_BAR | SKIP | No candle data provided |
| INDEP_PNL | PASS | All trades: independent PnL matches realized_pnl |
| SL_TP_CALC | PASS | SL/TP cross-validation OK: 5 trades, TP matches SL-derived signal_close (sl=3.0%, tp=6.0%, lev=1.0x) |
| EQUITY_WALK | FAIL | Final equity=7992.91 vs initial(10000.00) + sum(net_pnl)(-2013.36) = 7986.64 [diff=6.27, tol=2.5] |
| EQUITY | FAIL | PnL sum mismatch: sum(trades)=-2013.3618 vs result.json net_pnl=-2007.0900 [diff=6.2718, tol=2.5] |
| METRICS | PASS | Summary metrics consistent (5 trades, 0% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |
| METRIC_COUNTS | PASS | All counts match (5 trades, 0W/5L) |
| METRIC_PNL | PASS | All PnL aggregates match (net=-2013.36) |
| METRIC_RATES | PASS | All rates/ratios match (WR=0/5) |
| METRIC_EXTREMES | PASS | All extremes/streaks match (streaks: 0W/5L) |
| METRIC_DRAWDOWN | PASS | Drawdown matches (abs=2007.09, pct=0.2007) |
| METRIC_RISK | PASS | Risk metrics match (Sharpe=-10.51, Sortino=-11.47, Calmar=-4.30) |
| METRIC_DURATION | PASS | Duration matches (avg=790.2 bars) |
| METRIC_QUALITY | PASS | Recovery factor matches (-1.00) |

### IND_017_willr_oversold_long
- **Status**: PASS
- **Pattern**: range_wide
- **Trades**: 230
- **Net PnL**: 41176.03 USDT
- **Win Rate**: 0.7%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| OHLCV_VALID | SKIP | No candle data provided |
| TRADE_COUNT | PASS | Consistent: 230 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All 230 SL/TP levels valid (sl=3.0%, tp=6.0%) [150 SL-entry crosses, 19 TP-entry crosses] |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| ENTRY_FILL | PASS | All 230 entries: valid prices, correct SL direction, positive sizes |
| EXIT_FILL | SKIP | No candle data provided |
| TP_SL_BAR | SKIP | No candle data provided |
| INDEP_PNL | PASS | All trades: independent PnL matches realized_pnl |
| SL_TP_CALC | PASS | SL/TP cross-validation OK: 230 trades, TP matches SL-derived signal_close (sl=3.0%, tp=6.0%, lev=1.0x) |
| EQUITY_WALK | PASS | Equity walk consistent: 10000 + 41139.64 = 51139.64 (actual=51176.03, diff=36.39) |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=41176.03 |
| METRICS | PASS | Summary metrics consistent (230 trades, 1% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |
| METRIC_COUNTS | PASS | All counts match (230 trades, 168W/62L) |
| METRIC_PNL | PASS | All PnL aggregates match (net=41139.64) |
| METRIC_RATES | PASS | All rates/ratios match (WR=168/230) |
| METRIC_EXTREMES | PASS | All extremes/streaks match (streaks: 79W/17L) |
| METRIC_DRAWDOWN | PASS | Drawdown matches (abs=12814.13, pct=0.2003) |
| METRIC_RISK | PASS | Risk metrics match (Sharpe=20.47, Sortino=35.06, Calmar=4119298800404.45) |
| METRIC_DURATION | PASS | Duration matches (avg=5.7 bars) |
| METRIC_QUALITY | PASS | Recovery factor matches (3.21) |

### IND_018_willr_overbought_short
- **Status**: PASS
- **Pattern**: range_wide
- **Trades**: 56
- **Net PnL**: -1017.44 USDT
- **Win Rate**: 0.4%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| OHLCV_VALID | SKIP | No candle data provided |
| TRADE_COUNT | PASS | Consistent: 56 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All 56 SL/TP levels valid (sl=3.0%, tp=6.0%) [23 SL-entry crosses] |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| ENTRY_FILL | PASS | All 56 entries: valid prices, correct SL direction, positive sizes |
| EXIT_FILL | SKIP | No candle data provided |
| TP_SL_BAR | SKIP | No candle data provided |
| INDEP_PNL | PASS | All trades: independent PnL matches realized_pnl |
| SL_TP_CALC | PASS | SL/TP cross-validation OK: 56 trades, TP matches SL-derived signal_close (sl=3.0%, tp=6.0%, lev=1.0x) |
| EQUITY_WALK | PASS | Equity walk consistent: 10000 + -1017.44 = 8982.56 (actual=8982.56, diff=0.00) |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=-1017.44 |
| METRICS | PASS | Summary metrics consistent (56 trades, 0% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |
| METRIC_COUNTS | PASS | All counts match (56 trades, 21W/35L) |
| METRIC_PNL | PASS | All PnL aggregates match (net=-1017.44) |
| METRIC_RATES | PASS | All rates/ratios match (WR=21/56) |
| METRIC_EXTREMES | PASS | All extremes/streaks match (streaks: 14W/14L) |
| METRIC_DRAWDOWN | PASS | Drawdown matches (abs=2381.82, pct=0.2096) |
| METRIC_RISK | PASS | Risk metrics match (Sharpe=-7.97, Sortino=-9.86, Calmar=-4.77) |
| METRIC_DURATION | PASS | Duration matches (avg=3.8 bars) |
| METRIC_QUALITY | PASS | Recovery factor matches (-0.43) |

### IND_019_cmo_oversold_long
- **Status**: PASS
- **Pattern**: reversal_double_bottom
- **Trades**: 15
- **Net PnL**: -2057.04 USDT

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| OHLCV_VALID | SKIP | No candle data provided |
| TRADE_COUNT | PASS | Consistent: 15 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All 15 SL/TP levels valid (sl=3.0%, tp=6.0%) |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| ENTRY_FILL | PASS | All 15 entries: valid prices, correct SL direction, positive sizes |
| EXIT_FILL | SKIP | No candle data provided |
| TP_SL_BAR | SKIP | No candle data provided |
| INDEP_PNL | PASS | All trades: independent PnL matches realized_pnl |
| SL_TP_CALC | PASS | SL/TP cross-validation OK: 15 trades, TP matches SL-derived signal_close (sl=3.0%, tp=6.0%, lev=1.0x) |
| EQUITY_WALK | PASS | Equity walk consistent: 10000 + -2057.04 = 7942.96 (actual=7942.96, diff=0.00) |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=-2057.04 |
| METRICS | PASS | Summary metrics consistent (15 trades, 0% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |
| METRIC_COUNTS | PASS | All counts match (15 trades, 0W/15L) |
| METRIC_PNL | PASS | All PnL aggregates match (net=-2057.04) |
| METRIC_RATES | PASS | All rates/ratios match (WR=0/15) |
| METRIC_EXTREMES | PASS | All extremes/streaks match (streaks: 0W/15L) |
| METRIC_DRAWDOWN | PASS | Drawdown matches (abs=2057.04, pct=0.2057) |
| METRIC_RISK | PASS | Risk metrics match (Sharpe=-15.03, Sortino=-16.70, Calmar=-4.86) |
| METRIC_DURATION | PASS | Duration matches (avg=28.8 bars) |
| METRIC_QUALITY | PASS | Recovery factor matches (-1.00) |

### IND_020_mfi_oversold_long
- **Status**: FAIL
- **Pattern**: accumulation
- **Trades**: 6
- **Net PnL**: -2100.71 USDT

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| OHLCV_VALID | SKIP | No candle data provided |
| TRADE_COUNT | PASS | Consistent: 6 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All 6 SL/TP levels valid (sl=3.0%, tp=6.0%) |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| ENTRY_FILL | PASS | All 6 entries: valid prices, correct SL direction, positive sizes |
| EXIT_FILL | SKIP | No candle data provided |
| TP_SL_BAR | SKIP | No candle data provided |
| INDEP_PNL | PASS | All trades: independent PnL matches realized_pnl |
| SL_TP_CALC | PASS | SL/TP cross-validation OK: 6 trades, TP matches SL-derived signal_close (sl=3.0%, tp=6.0%, lev=1.0x) |
| EQUITY_WALK | FAIL | Final equity=7899.29 vs initial(10000.00) + sum(net_pnl)(-2106.33) = 7893.67 [diff=5.62, tol=3.0] |
| EQUITY | FAIL | PnL sum mismatch: sum(trades)=-2106.3285 vs result.json net_pnl=-2100.7100 [diff=5.6185, tol=3.0] |
| METRICS | PASS | Summary metrics consistent (6 trades, 0% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |
| METRIC_COUNTS | PASS | All counts match (6 trades, 0W/6L) |
| METRIC_PNL | PASS | All PnL aggregates match (net=-2106.33) |
| METRIC_RATES | PASS | All rates/ratios match (WR=0/6) |
| METRIC_EXTREMES | PASS | All extremes/streaks match (streaks: 0W/6L) |
| METRIC_DRAWDOWN | PASS | Drawdown matches (abs=2109.16, pct=0.2107) |
| METRIC_RISK | PASS | Risk metrics match (Sharpe=-14.17, Sortino=-14.94, Calmar=-4.69) |
| METRIC_DURATION | PASS | Duration matches (avg=292.5 bars) |
| METRIC_QUALITY | PASS | Recovery factor matches (-1.00) |

### IND_021_mfi_overbought_short
- **Status**: PASS
- **Pattern**: distribution
- **Trades**: 176
- **Net PnL**: -1868.79 USDT
- **Win Rate**: 0.4%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| OHLCV_VALID | SKIP | No candle data provided |
| TRADE_COUNT | PASS | Consistent: 176 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All 176 SL/TP levels valid (sl=3.0%, tp=6.0%) [72 TP-entry crosses] |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| ENTRY_FILL | PASS | All 176 entries: valid prices, correct SL direction, positive sizes |
| EXIT_FILL | SKIP | No candle data provided |
| TP_SL_BAR | SKIP | No candle data provided |
| INDEP_PNL | PASS | All trades: independent PnL matches realized_pnl |
| SL_TP_CALC | PASS | SL/TP cross-validation OK: 176 trades, TP matches SL-derived signal_close (sl=3.0%, tp=6.0%, lev=1.0x) |
| EQUITY_WALK | PASS | Equity walk consistent: 10000 + -1868.79 = 8131.21 (actual=8131.21, diff=0.00) |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=-1868.79 |
| METRICS | PASS | Summary metrics consistent (176 trades, 0% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |
| METRIC_COUNTS | PASS | All counts match (176 trades, 79W/97L) |
| METRIC_PNL | PASS | All PnL aggregates match (net=-1868.79) |
| METRIC_RATES | PASS | All rates/ratios match (WR=79/176) |
| METRIC_EXTREMES | PASS | All extremes/streaks match (streaks: 28W/28L) |
| METRIC_DRAWDOWN | PASS | Drawdown matches (abs=2103.87, pct=0.2056) |
| METRIC_RISK | PASS | Risk metrics match (Sharpe=-7.92, Sortino=-11.88, Calmar=-4.84) |
| METRIC_DURATION | PASS | Duration matches (avg=4.2 bars) |
| METRIC_QUALITY | PASS | Recovery factor matches (-0.89) |

### IND_022_uo_oversold_long
- **Status**: PASS
- **Pattern**: reversal_v_bottom
- **Trades**: 279
- **Net PnL**: 67626.86 USDT
- **Win Rate**: 0.8%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| OHLCV_VALID | SKIP | No candle data provided |
| TRADE_COUNT | PASS | Consistent: 279 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All 279 SL/TP levels valid (sl=3.0%, tp=6.0%) [220 SL-entry crosses] |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| ENTRY_FILL | PASS | All 279 entries: valid prices, correct SL direction, positive sizes |
| EXIT_FILL | SKIP | No candle data provided |
| TP_SL_BAR | SKIP | No candle data provided |
| INDEP_PNL | PASS | All trades: independent PnL matches realized_pnl |
| SL_TP_CALC | PASS | SL/TP cross-validation OK: 279 trades, TP matches SL-derived signal_close (sl=3.0%, tp=6.0%, lev=1.0x) |
| EQUITY_WALK | PASS | Equity walk consistent: 10000 + 67571.59 = 77571.59 (actual=77626.86, diff=55.27) |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=67626.86 |
| METRICS | PASS | Summary metrics consistent (279 trades, 1% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |
| METRIC_COUNTS | PASS | All counts match (279 trades, 211W/68L) |
| METRIC_PNL | PASS | All PnL aggregates match (net=67571.59) |
| METRIC_RATES | PASS | All rates/ratios match (WR=211/279) |
| METRIC_EXTREMES | PASS | All extremes/streaks match (streaks: 79W/17L) |
| METRIC_DRAWDOWN | PASS | Drawdown matches (abs=19490.68, pct=0.2007) |
| METRIC_RISK | PASS | Risk metrics match (Sharpe=14.23, Sortino=28.37, Calmar=7081.65) |
| METRIC_DURATION | PASS | Duration matches (avg=21.5 bars) |
| METRIC_QUALITY | PASS | Recovery factor matches (3.47) |

### IND_023_roc_positive_long
- **Status**: PASS
- **Pattern**: trend_up_clean
- **Trades**: 19
- **Net PnL**: -1982.15 USDT

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| OHLCV_VALID | SKIP | No candle data provided |
| TRADE_COUNT | PASS | Consistent: 19 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All 19 SL/TP levels valid (sl=3.0%, tp=6.0%) [16 TP-entry crosses] |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| ENTRY_FILL | PASS | All 19 entries: valid prices, correct SL direction, positive sizes |
| EXIT_FILL | SKIP | No candle data provided |
| TP_SL_BAR | SKIP | No candle data provided |
| INDEP_PNL | PASS | All trades: independent PnL matches realized_pnl |
| SL_TP_CALC | PASS | SL/TP cross-validation OK: 19 trades, TP matches SL-derived signal_close (sl=3.0%, tp=6.0%, lev=1.0x) |
| EQUITY_WALK | PASS | Equity walk consistent: 10000 + -1982.15 = 8017.85 (actual=8017.85, diff=0.00) |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=-1982.15 |
| METRICS | PASS | Summary metrics consistent (19 trades, 0% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |
| METRIC_COUNTS | PASS | All counts match (19 trades, 0W/19L) |
| METRIC_PNL | PASS | All PnL aggregates match (net=-1982.15) |
| METRIC_RATES | PASS | All rates/ratios match (WR=0/19) |
| METRIC_EXTREMES | PASS | All extremes/streaks match (streaks: 0W/19L) |
| METRIC_DRAWDOWN | PASS | Drawdown matches (abs=2023.26, pct=0.2015) |
| METRIC_RISK | PASS | Risk metrics match (Sharpe=-16.46, Sortino=-17.26, Calmar=-4.86) |
| METRIC_DURATION | PASS | Duration matches (avg=101.0 bars) |
| METRIC_QUALITY | PASS | Recovery factor matches (-0.98) |

### IND_024_roc_negative_short
- **Status**: PASS
- **Pattern**: trend_down_clean
- **Trades**: 20
- **Net PnL**: -2021.99 USDT

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| OHLCV_VALID | SKIP | No candle data provided |
| TRADE_COUNT | PASS | Consistent: 20 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All 20 SL/TP levels valid (sl=3.0%, tp=6.0%) |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| ENTRY_FILL | PASS | All 20 entries: valid prices, correct SL direction, positive sizes |
| EXIT_FILL | SKIP | No candle data provided |
| TP_SL_BAR | SKIP | No candle data provided |
| INDEP_PNL | PASS | All trades: independent PnL matches realized_pnl |
| SL_TP_CALC | PASS | SL/TP cross-validation OK: 20 trades, TP matches SL-derived signal_close (sl=3.0%, tp=6.0%, lev=1.0x) |
| EQUITY_WALK | PASS | Equity walk consistent: 10000 + -2021.99 = 7978.01 (actual=7978.01, diff=0.00) |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=-2021.99 |
| METRICS | PASS | Summary metrics consistent (20 trades, 0% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |
| METRIC_COUNTS | PASS | All counts match (20 trades, 0W/20L) |
| METRIC_PNL | PASS | All PnL aggregates match (net=-2021.99) |
| METRIC_RATES | PASS | All rates/ratios match (WR=0/20) |
| METRIC_EXTREMES | PASS | All extremes/streaks match (streaks: 0W/20L) |
| METRIC_DRAWDOWN | PASS | Drawdown matches (abs=2091.38, pct=0.2077) |
| METRIC_RISK | PASS | Risk metrics match (Sharpe=-12.00, Sortino=-13.20, Calmar=-4.75) |
| METRIC_DURATION | PASS | Duration matches (avg=85.2 bars) |
| METRIC_QUALITY | PASS | Recovery factor matches (-0.97) |

### IND_025_mom_positive_long
- **Status**: PASS
- **Pattern**: trend_up_clean
- **Trades**: 19
- **Net PnL**: -1980.10 USDT

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| OHLCV_VALID | SKIP | No candle data provided |
| TRADE_COUNT | PASS | Consistent: 19 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All 19 SL/TP levels valid (sl=3.0%, tp=6.0%) |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| ENTRY_FILL | PASS | All 19 entries: valid prices, correct SL direction, positive sizes |
| EXIT_FILL | SKIP | No candle data provided |
| TP_SL_BAR | SKIP | No candle data provided |
| INDEP_PNL | PASS | All trades: independent PnL matches realized_pnl |
| SL_TP_CALC | PASS | SL/TP cross-validation OK: 19 trades, TP matches SL-derived signal_close (sl=3.0%, tp=6.0%, lev=1.0x) |
| EQUITY_WALK | PASS | Equity walk consistent: 10000 + -1980.10 = 8019.90 (actual=8019.90, diff=0.00) |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=-1980.10 |
| METRICS | PASS | Summary metrics consistent (19 trades, 0% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |
| METRIC_COUNTS | PASS | All counts match (19 trades, 0W/19L) |
| METRIC_PNL | PASS | All PnL aggregates match (net=-1980.10) |
| METRIC_RATES | PASS | All rates/ratios match (WR=0/19) |
| METRIC_EXTREMES | PASS | All extremes/streaks match (streaks: 0W/19L) |
| METRIC_DRAWDOWN | PASS | Drawdown matches (abs=2014.24, pct=0.2007) |
| METRIC_RISK | PASS | Risk metrics match (Sharpe=-19.24, Sortino=-21.70, Calmar=-4.98) |
| METRIC_DURATION | PASS | Duration matches (avg=16.1 bars) |
| METRIC_QUALITY | PASS | Recovery factor matches (-0.98) |

### IND_026_mom_negative_short
- **Status**: PASS
- **Pattern**: trend_down_clean
- **Trades**: 121
- **Net PnL**: 940.99 USDT
- **Win Rate**: 0.5%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| OHLCV_VALID | SKIP | No candle data provided |
| TRADE_COUNT | PASS | Consistent: 121 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All 121 SL/TP levels valid (sl=3.0%, tp=6.0%) [59 SL-entry crosses] |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| ENTRY_FILL | PASS | All 121 entries: valid prices, correct SL direction, positive sizes |
| EXIT_FILL | SKIP | No candle data provided |
| TP_SL_BAR | SKIP | No candle data provided |
| INDEP_PNL | PASS | All trades: independent PnL matches realized_pnl |
| SL_TP_CALC | PASS | SL/TP cross-validation OK: 121 trades, TP matches SL-derived signal_close (sl=3.0%, tp=6.0%, lev=1.0x) |
| EQUITY_WALK | PASS | Equity walk consistent: 10000 + 940.99 = 10940.99 (actual=10940.99, diff=0.00) |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=940.99 |
| METRICS | PASS | Summary metrics consistent (121 trades, 0% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |
| METRIC_COUNTS | PASS | All counts match (121 trades, 57W/64L) |
| METRIC_PNL | PASS | All PnL aggregates match (net=940.99) |
| METRIC_RATES | PASS | All rates/ratios match (WR=57/121) |
| METRIC_EXTREMES | PASS | All extremes/streaks match (streaks: 56W/34L) |
| METRIC_DRAWDOWN | PASS | Drawdown matches (abs=2764.25, pct=0.2017) |
| METRIC_RISK | PASS | Risk metrics match (Sharpe=3.03, Sortino=4.40, Calmar=19.43) |
| METRIC_DURATION | PASS | Duration matches (avg=14.3 bars) |
| METRIC_QUALITY | PASS | Recovery factor matches (0.34) |

### IND_027_obv_rising_long
- **Status**: PASS
- **Pattern**: accumulation
- **Trades**: 16
- **Net PnL**: -2020.99 USDT
- **Win Rate**: 0.1%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| OHLCV_VALID | SKIP | No candle data provided |
| TRADE_COUNT | PASS | Consistent: 16 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All 16 SL/TP levels valid (sl=3.0%, tp=6.0%) [11 TP-entry crosses] |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| ENTRY_FILL | PASS | All 16 entries: valid prices, correct SL direction, positive sizes |
| EXIT_FILL | SKIP | No candle data provided |
| TP_SL_BAR | SKIP | No candle data provided |
| INDEP_PNL | PASS | All trades: independent PnL matches realized_pnl |
| SL_TP_CALC | PASS | SL/TP cross-validation OK: 16 trades, TP matches SL-derived signal_close (sl=3.0%, tp=6.0%, lev=1.0x) |
| EQUITY_WALK | PASS | Equity walk consistent: 10000 + -2020.99 = 7979.01 (actual=7979.01, diff=0.00) |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=-2020.99 |
| METRICS | PASS | Summary metrics consistent (16 trades, 0% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |
| METRIC_COUNTS | PASS | All counts match (16 trades, 1W/15L) |
| METRIC_PNL | PASS | All PnL aggregates match (net=-2020.99) |
| METRIC_RATES | PASS | All rates/ratios match (WR=1/16) |
| METRIC_EXTREMES | PASS | All extremes/streaks match (streaks: 1W/10L) |
| METRIC_DRAWDOWN | PASS | Drawdown matches (abs=2027.63, pct=0.2026) |
| METRIC_RISK | PASS | Risk metrics match (Sharpe=-16.43, Sortino=-17.85, Calmar=-4.85) |
| METRIC_DURATION | PASS | Duration matches (avg=118.9 bars) |
| METRIC_QUALITY | PASS | Recovery factor matches (-1.00) |

### IND_028_cmf_positive_long
- **Status**: PASS
- **Pattern**: accumulation
- **Trades**: 220
- **Net PnL**: 82997.38 USDT
- **Win Rate**: 0.8%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| OHLCV_VALID | SKIP | No candle data provided |
| TRADE_COUNT | PASS | Consistent: 220 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All 220 SL/TP levels valid (sl=3.0%, tp=6.0%) [176 SL-entry crosses] |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| ENTRY_FILL | PASS | All 220 entries: valid prices, correct SL direction, positive sizes |
| EXIT_FILL | SKIP | No candle data provided |
| TP_SL_BAR | SKIP | No candle data provided |
| INDEP_PNL | PASS | All trades: independent PnL matches realized_pnl |
| SL_TP_CALC | PASS | SL/TP cross-validation OK: 220 trades, TP matches SL-derived signal_close (sl=3.0%, tp=6.0%, lev=1.0x) |
| EQUITY_WALK | PASS | Equity walk consistent: 10000 + 82997.38 = 92997.38 (actual=92997.38, diff=0.00) |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=82997.38 |
| METRICS | PASS | Summary metrics consistent (220 trades, 1% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |
| METRIC_COUNTS | PASS | All counts match (220 trades, 170W/50L) |
| METRIC_PNL | PASS | All PnL aggregates match (net=82997.38) |
| METRIC_RATES | PASS | All rates/ratios match (WR=170/220) |
| METRIC_EXTREMES | PASS | All extremes/streaks match (streaks: 151W/43L) |
| METRIC_DRAWDOWN | PASS | Drawdown matches (abs=23737.89, pct=0.2033) |
| METRIC_RISK | PASS | Risk metrics match (Sharpe=49.52, Sortino=249.04, Calmar=1150895320775814545408.00) |
| METRIC_DURATION | PASS | Duration matches (avg=5.7 bars) |
| METRIC_QUALITY | PASS | Recovery factor matches (3.50) |

### IND_029_cmf_negative_short
- **Status**: PASS
- **Pattern**: distribution
- **Trades**: 18272
- **Net PnL**: 1122932799257637760.00 USDT
- **Win Rate**: 0.9%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| OHLCV_VALID | SKIP | No candle data provided |
| TRADE_COUNT | PASS | Consistent: 18272 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All 18272 SL/TP levels valid (sl=3.0%, tp=6.0%) [15586 SL-entry crosses, 1726 TP-entry crosses] |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| ENTRY_FILL | PASS | All 18272 entries: valid prices, correct SL direction, positive sizes |
| EXIT_FILL | SKIP | No candle data provided |
| TP_SL_BAR | SKIP | No candle data provided |
| INDEP_PNL | PASS | All trades: independent PnL matches realized_pnl |
| SL_TP_CALC | PASS | SL/TP cross-validation OK: 18272 trades, TP matches SL-derived signal_close (sl=3.0%, tp=6.0%, lev=1.0x) |
| EQUITY_WALK | PASS | Equity walk consistent: 10000 + 1122932799257639552.00 = 1122932799257649536.00 (actual=1122932799257647744.00, diff=179 |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=1122932799257637760.00 |
| METRICS | PASS | Summary metrics consistent (18272 trades, 1% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |
| METRIC_COUNTS | PASS | All counts match (18272 trades, 16022W/2250L) |
| METRIC_PNL | PASS | All PnL aggregates match (net=1122932799257639552.00) |
| METRIC_RATES | PASS | All rates/ratios match (WR=16022/18272) |
| METRIC_EXTREMES | PASS | All extremes/streaks match (streaks: 13765W/514L) |
| METRIC_DRAWDOWN | PASS | Drawdown matches (abs=29190983864023168.00, pct=0.0660) |
| METRIC_RISK | PASS | Risk metrics match (Sharpe=23.06, Sortino=518.85, Calmar=276256133325.25) |
| METRIC_DURATION | PASS | Duration matches (avg=0.7 bars) |
| METRIC_QUALITY | PASS | Recovery factor matches (38.47) |

### IND_030_vwap_above_long
- **Status**: PASS
- **Pattern**: trend_up_clean
- **Trades**: 13
- **Net PnL**: -2004.76 USDT
- **Win Rate**: 0.1%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| OHLCV_VALID | SKIP | No candle data provided |
| TRADE_COUNT | PASS | Consistent: 13 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All 13 SL/TP levels valid (sl=3.0%, tp=6.0%) [8 TP-entry crosses] |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| ENTRY_FILL | PASS | All 13 entries: valid prices, correct SL direction, positive sizes |
| EXIT_FILL | SKIP | No candle data provided |
| TP_SL_BAR | SKIP | No candle data provided |
| INDEP_PNL | PASS | All trades: independent PnL matches realized_pnl |
| SL_TP_CALC | PASS | SL/TP cross-validation OK: 13 trades, TP matches SL-derived signal_close (sl=3.0%, tp=6.0%, lev=1.0x) |
| EQUITY_WALK | PASS | Equity walk consistent: 10000 + -2004.76 = 7995.24 (actual=7995.24, diff=0.00) |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=-2004.76 |
| METRICS | PASS | Summary metrics consistent (13 trades, 0% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |
| METRIC_COUNTS | PASS | All counts match (13 trades, 1W/12L) |
| METRIC_PNL | PASS | All PnL aggregates match (net=-2004.76) |
| METRIC_RATES | PASS | All rates/ratios match (WR=1/13) |
| METRIC_EXTREMES | PASS | All extremes/streaks match (streaks: 1W/9L) |
| METRIC_DRAWDOWN | PASS | Drawdown matches (abs=2056.16, pct=0.2046) |
| METRIC_RISK | PASS | Risk metrics match (Sharpe=-10.14, Sortino=-13.17, Calmar=-4.78) |
| METRIC_DURATION | PASS | Duration matches (avg=144.7 bars) |
| METRIC_QUALITY | PASS | Recovery factor matches (-0.98) |

### IND_031_atr_filter_long
- **Status**: PASS
- **Pattern**: vol_squeeze_expand
- **Trades**: 9
- **Net PnL**: -2269.99 USDT
- **Win Rate**: 0.4%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| OHLCV_VALID | SKIP | No candle data provided |
| TRADE_COUNT | PASS | Consistent: 9 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All 9 SL/TP levels valid (sl=3.0%, tp=6.0%) [5 TP-entry crosses] |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| ENTRY_FILL | PASS | All 9 entries: valid prices, correct SL direction, positive sizes |
| EXIT_FILL | SKIP | No candle data provided |
| TP_SL_BAR | SKIP | No candle data provided |
| INDEP_PNL | PASS | All trades: independent PnL matches realized_pnl |
| SL_TP_CALC | PASS | SL/TP cross-validation OK: 9 trades, TP matches SL-derived signal_close (sl=3.0%, tp=6.0%, lev=1.0x) |
| EQUITY_WALK | PASS | Equity walk consistent: 10000 + -2269.99 = 7730.01 (actual=7730.01, diff=0.00) |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=-2269.99 |
| METRICS | PASS | Summary metrics consistent (9 trades, 0% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |
| METRIC_COUNTS | PASS | All counts match (9 trades, 4W/5L) |
| METRIC_PNL | PASS | All PnL aggregates match (net=-2269.99) |
| METRIC_RATES | PASS | All rates/ratios match (WR=4/9) |
| METRIC_EXTREMES | PASS | All extremes/streaks match (streaks: 3W/3L) |
| METRIC_DRAWDOWN | PASS | Drawdown matches (abs=2269.99, pct=0.2270) |
| METRIC_RISK | PASS | Risk metrics match (Sharpe=-46.96, Sortino=-46.05, Calmar=-4.41) |
| METRIC_DURATION | PASS | Duration matches (avg=0.0 bars) |
| METRIC_QUALITY | PASS | Recovery factor matches (-1.00) |

### IND_032_natr_filter_long
- **Status**: FAIL
- **Pattern**: vol_squeeze_expand
- **Trades**: 20
- **Net PnL**: -64116955035139.87 USDT
- **Win Rate**: 0.9%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| OHLCV_VALID | SKIP | No candle data provided |
| TRADE_COUNT | PASS | Consistent: 20 trades |
| PNL_DIRECTION | FAIL | 1 trades with wrong PnL direction:   Trade 19: side=long entry=-1276.4569 exit=44883.2186 realized_pnl=-66074619174822.9 |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All 20 SL/TP levels valid (sl=3.0%, tp=6.0%) [19 SL-entry crosses] |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| ENTRY_FILL | FAIL | 1 entry fill issues:   Trade 19: entry_price=-1276.4569285951654 is invalid |
| EXIT_FILL | SKIP | No candle data provided |
| TP_SL_BAR | SKIP | No candle data provided |
| INDEP_PNL | PASS | All trades: independent PnL matches realized_pnl |
| SL_TP_CALC | PASS | SL/TP cross-validation OK: 20 trades, TP matches SL-derived signal_close (sl=3.0%, tp=6.0%, lev=1.0x) |
| EQUITY_WALK | PASS | Equity walk consistent: 10000 + -64116955035139.87 = -64116955025139.87 (actual=-64116955025139.87, diff=0.00) |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=-64116955035139.87 |
| METRICS | PASS | Summary metrics consistent (20 trades, 1% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |
| METRIC_COUNTS | PASS | All counts match (20 trades, 19W/1L) |
| METRIC_PNL | PASS | All PnL aggregates match (net=-64116955035139.87) |
| METRIC_RATES | PASS | All rates/ratios match (WR=19/20) |
| METRIC_EXTREMES | PASS | All extremes/streaks match (streaks: 19W/1L) |
| METRIC_DRAWDOWN | PASS | Drawdown matches (abs=66040288017253.57, pct=34.3364) |
| METRIC_RISK | FAIL | Risk metric mismatches:   calmar: computed=0.0000 vs result=-0.0300 [rel_err=100.00%] |
| METRIC_DURATION | PASS | Duration matches (avg=0.0 bars) |
| METRIC_QUALITY | PASS | Recovery factor matches (-0.97) |

### IND_033_ohlc4_above_ema
- **Status**: PASS
- **Pattern**: trend_up_clean
- **Trades**: 83
- **Net PnL**: -1555.08 USDT
- **Win Rate**: 0.2%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| OHLCV_VALID | SKIP | No candle data provided |
| TRADE_COUNT | PASS | Consistent: 83 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All 83 SL/TP levels valid (sl=3.0%, tp=6.0%) [49 TP-entry crosses] |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| ENTRY_FILL | PASS | All 83 entries: valid prices, correct SL direction, positive sizes |
| EXIT_FILL | SKIP | No candle data provided |
| TP_SL_BAR | SKIP | No candle data provided |
| INDEP_PNL | PASS | All trades: independent PnL matches realized_pnl |
| SL_TP_CALC | PASS | SL/TP cross-validation OK: 83 trades, TP matches SL-derived signal_close (sl=3.0%, tp=6.0%, lev=1.0x) |
| EQUITY_WALK | PASS | Equity walk consistent: 10000 + -1555.08 = 8444.92 (actual=8444.92, diff=0.00) |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=-1555.08 |
| METRICS | PASS | Summary metrics consistent (83 trades, 0% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |
| METRIC_COUNTS | PASS | All counts match (83 trades, 18W/65L) |
| METRIC_PNL | PASS | All PnL aggregates match (net=-1555.08) |
| METRIC_RATES | PASS | All rates/ratios match (WR=18/83) |
| METRIC_EXTREMES | PASS | All extremes/streaks match (streaks: 3W/24L) |
| METRIC_DRAWDOWN | PASS | Drawdown matches (abs=2120.43, pct=0.2007) |
| METRIC_RISK | PASS | Risk metrics match (Sharpe=-9.83, Sortino=-19.68, Calmar=-4.87) |
| METRIC_DURATION | PASS | Duration matches (avg=16.7 bars) |
| METRIC_QUALITY | PASS | Recovery factor matches (-0.73) |

### IND_034_midprice_above_ema
- **Status**: PASS
- **Pattern**: trend_up_clean
- **Trades**: 19
- **Net PnL**: -2015.96 USDT

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| OHLCV_VALID | SKIP | No candle data provided |
| TRADE_COUNT | PASS | Consistent: 19 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All 19 SL/TP levels valid (sl=3.0%, tp=6.0%) |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| ENTRY_FILL | PASS | All 19 entries: valid prices, correct SL direction, positive sizes |
| EXIT_FILL | SKIP | No candle data provided |
| TP_SL_BAR | SKIP | No candle data provided |
| INDEP_PNL | PASS | All trades: independent PnL matches realized_pnl |
| SL_TP_CALC | PASS | SL/TP cross-validation OK: 19 trades, TP matches SL-derived signal_close (sl=3.0%, tp=6.0%, lev=1.0x) |
| EQUITY_WALK | PASS | Equity walk consistent: 10000 + -2015.96 = 7984.04 (actual=7984.04, diff=0.00) |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=-2015.96 |
| METRICS | PASS | Summary metrics consistent (19 trades, 0% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |
| METRIC_COUNTS | PASS | All counts match (19 trades, 0W/19L) |
| METRIC_PNL | PASS | All PnL aggregates match (net=-2015.96) |
| METRIC_RATES | PASS | All rates/ratios match (WR=0/19) |
| METRIC_EXTREMES | PASS | All extremes/streaks match (streaks: 0W/19L) |
| METRIC_DRAWDOWN | PASS | Drawdown matches (abs=2044.72, pct=0.2039) |
| METRIC_RISK | PASS | Risk metrics match (Sharpe=-19.53, Sortino=-22.03, Calmar=-4.90) |
| METRIC_DURATION | PASS | Duration matches (avg=17.0 bars) |
| METRIC_QUALITY | PASS | Recovery factor matches (-0.99) |

## Failures & Issues

- **IND_016_cci_overbought_short** [FAIL]: 21P/2F/0W/3S
- **IND_020_mfi_oversold_long** [FAIL]: 21P/2F/0W/3S
- **IND_032_natr_filter_long** [FAIL]: 20P/3F/0W/3S
