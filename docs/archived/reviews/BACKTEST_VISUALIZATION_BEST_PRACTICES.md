# Backtest Visualization Best Practices

**Date**: 2026-01-06
**Purpose**: Research findings on professional trading performance visualization

---

## Executive Summary

Professional backtest visualization goes far beyond simple equity curves. The best platforms combine **multiple chart types**, **interactive exploration**, and **risk-adjusted metrics** to help traders understand not just *what* happened, but *why* and *what could happen*.

Key findings:
1. **Equity + Drawdown** should always be shown together
2. **MAE/MFE analysis** is critical for stop/target optimization
3. **Calendar heatmaps** reveal behavioral patterns
4. **Monte Carlo simulation** provides realistic risk expectations
5. **Trade scatter plots** show duration vs. profit relationships

---

## 1. Core Visualizations (Must-Have)

### 1.1 Equity Curve with Drawdown Overlay

The equity curve is "one of the first things to look at when evaluating strategy performance because its visual nature delivers information that no other performance numbers could easily match." ([FasterCapital](https://fastercapital.com/content/Equity-Curve-Backtesting--Evaluating-Strategies-for-Profitability.html))

**Best Practices:**
- Plot equity curve on top panel, drawdown (underwater curve) below
- Use color gradients for drawdown severity (light red → dark red)
- Include benchmark comparison (e.g., buy-and-hold, S&P 500)
- "Your equity curve should look like a staircase, not a rollercoaster" - volatile curves suggest scalability issues

**Implementation (from [PyQuantLab](https://pyquantlab.medium.com/equity-curve-max-drawdown-on-one-chart-with-matplotlib-1f6a40a8ac99)):**
```python
# Two-panel layout
fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, height_ratios=[3, 1])
ax1.plot(equity_curve, label='Strategy')
ax1.plot(benchmark, label='Benchmark', alpha=0.7)
ax2.fill_between(drawdown.index, drawdown.values, color='red', alpha=0.3)
```

### 1.2 Trade Markers on Price Chart

Per [lightweight-charts GitHub discussion](https://github.com/tradingview/lightweight-charts/issues/1449), simple markers are insufficient. Professional visualization needs:

**Required Elements:**
- Entry/exit markers with direction (long/short)
- Stop loss and take profit levels as horizontal lines
- Transparent boxes showing trade duration and P/L zone
- Color coding: green for winners, red for losers

**Enhancement from Jesse-Research ([GitHub](https://github.com/deemzie/jesse-research)):**
- Interactive table of trades that expands to show orders on chart
- Click trade → zoom to that time period
- Display entry price, exit price, and P/L on hover

### 1.3 Returns Distribution Histogram

Show the distribution of trade returns with:
- Normal distribution overlay for comparison
- Vertical lines at mean, median, and zero
- Skewness and kurtosis annotations
- Separate histograms for winning vs. losing trades

---

## 2. Trade Quality Analysis (MAE/MFE)

### 2.1 Maximum Adverse Excursion (MAE)

MAE shows "what is the max amount of price movement against your favor in the duration of your trade" - essentially the maximum drawdown per position. ([TradingDiaryPro](https://www.tradingdiarypro.com/mae-mfe-explained/))

**MAE Scatter Plot:**
```
Y-axis: MAE (maximum loss during trade)
X-axis: Final P/L
Red dots: Losing trades
Green dots: Winning trades
```

**Interpretation ([TradesViz](https://www.tradesviz.com/blog/mfe-mae-charts/)):**
- "For a disciplined trader, the red dots should follow a diagonal line from origin to bottom-left"
- Dots far from the diagonal indicate stop losses are too wide
- Cluster analysis reveals optimal stop placement

### 2.2 Maximum Favorable Excursion (MFE)

MFE shows "what is the max amount of price movement in your favor" - the unrealized profit peak.

**Key Insight ([Trademetria](https://trademetria.com/blog/understanding-mae-and-mfe-metrics-a-guide-for-traders/)):**
> "If the distance between your MFE and trade price is too high, it means you are not capturing the full profitable move."

**MFE Analysis Charts:**
1. **MFE vs. Actual Profit scatter** - gap reveals "left on table"
2. **MFE Duration chart** - time to reach MFE ([TradesViz](https://www.tradesviz.com/blog/mfe-mae-duration/))
3. **MFE/MAE ratio by trade** - edge quality indicator

### 2.3 Our Current Data

We already capture MAE/MFE in `BacktestMetrics`:
```python
mae_avg_pct: float  # Average MAE as percentage
mfe_avg_pct: float  # Average MFE as percentage
```

**Visualization Opportunities:**
- Per-trade MAE/MFE in trade list
- Scatter plot: MAE vs. Final P/L
- Histogram: MFE - Actual Profit (unrealized potential)

---

## 3. Calendar & Time-Based Analysis

### 3.1 PnL Calendar Heatmap

"A PnL calendar displays your daily trading profit and loss in a calendar format, letting you spot patterns, streaks, and consistency issues at a glance." ([TradesViz](https://www.tradesviz.com/pnl-calendar/))

**Features:**
- Color-coded cells (green profit, red loss, intensity = magnitude)
- Monthly/weekly/yearly views
- Streak indicators (consecutive wins/losses)
- Filter by asset class

**Implementation:**
```
┌────┬────┬────┬────┬────┬────┬────┐
│ Su │ Mo │ Tu │ We │ Th │ Fr │ Sa │
├────┼────┼────┼────┼────┼────┼────┤
│    │+150│ -50│+200│+100│ -25│    │
│    │ ██ │ █  │ ███│ ██ │ █  │    │
└────┴────┴────┴────┴────┴────┴────┘
```

### 3.2 Time-of-Day / Day-of-Week Analysis

From [Tradervue](https://www.tradervue.com/site/trading-analysis):
> "See trades plotted in fine detail by trade duration, day/time, P&L, volume, or many other measures."

**Charts to Include:**
- Bar chart: Average P/L by hour of day
- Bar chart: Win rate by day of week
- Heatmap: Hour × Day performance matrix

### 3.3 Monthly Returns Heatmap

Per [Stock Rover](https://www.stockrover.com/help/analytics/monthly-returns-heatmap/):
> "The heatmap helps identify seasonality patterns, trends, and differences in portfolio performance over time."

**Format:**
```
       Jan   Feb   Mar   Apr   May   ...
2024  +5.2% -1.3% +3.8% +2.1% -0.5%
2025  +2.8% +4.1% -2.2% +6.3% +1.9%
```

---

## 4. Risk Analysis Visualizations

### 4.1 Rolling Performance Metrics

Instead of single values, show how metrics evolve:

| Metric | Window | Purpose |
|--------|--------|---------|
| Rolling Sharpe | 30-day | Consistency check |
| Rolling Win Rate | 20 trades | Regime detection |
| Rolling Avg Trade | 50 trades | Edge stability |
| Rolling Max DD | Expanding | Worst-case tracking |

### 4.2 Monte Carlo Simulation

"Monte Carlo analysis can help you estimate the risk and profitability of your trading strategy more realistically." ([StrategyQuant](https://strategyquant.com/blog/what-is-monte-carlo-analysis-and-why-you-should-use-it/))

**Visualization Elements:**
1. **Equity Curve Fan** - 1000 simulated paths
2. **Drawdown Distribution** - histogram of max DDs
3. **Probability of Ruin** - % of paths hitting threshold
4. **Confidence Bands** - 5th/95th percentile bounds

**Implementation ([HowToTrade](https://howtotrade.com/trading-tools/monte-carlo-simulation/)):**
```python
# Shuffle trade order 1000 times
for i in range(1000):
    shuffled = np.random.permutation(trades)
    equity = compute_equity(shuffled)
    simulations.append(equity)

# Plot percentile bands
p5 = np.percentile(simulations, 5, axis=0)
p95 = np.percentile(simulations, 95, axis=0)
ax.fill_between(x, p5, p95, alpha=0.3)
```

### 4.3 Risk/Reward Scatter Plot

From [PortfolioAnalytics](https://rdrr.io/cran/PortfolioAnalytics/man/chart.RiskReward.html):
> "Provide a visual representation of risk and return tradeoffs."

**Axes:**
- X: Risk measure (Volatility, Max DD, or VaR)
- Y: Return measure (CAGR, Sharpe, or Total Return)
- Point size: Number of trades or capital deployed

---

## 5. Trade-Level Analytics

### 5.1 Trade Duration vs. P/L

Scatter plot revealing:
- Optimal holding period
- Whether longer trades = better results
- Time-decay patterns

### 5.2 Position Size Analysis

From [TradingView Position Tool](https://www.tradingview.com/script/WGf6XZ6K-Position-Tool/):
- Risk per trade histogram
- Position size vs. outcome correlation
- Capital utilization over time

### 5.3 Win/Loss Streaks

Visual representation of consecutive outcomes:
```
W W W L L W W W W L W L L L W W
███████░░███████████░███░░░░█████
```

---

## 6. Dashboard Layout Recommendations

### 6.1 Overview Dashboard

```
┌─────────────────────────────────────────────────────────┐
│  SUMMARY CARDS (Net P/L, Win Rate, Sharpe, Max DD)      │
├─────────────────────────────────┬───────────────────────┤
│                                 │   Monthly Returns     │
│      Equity + Drawdown          │     Heatmap           │
│         (2/3 width)             │    (1/3 width)        │
├─────────────────────────────────┴───────────────────────┤
│              Trade List (sortable, filterable)          │
└─────────────────────────────────────────────────────────┘
```

### 6.2 Trade Analysis Dashboard

```
┌─────────────────────────────────────────────────────────┐
│              Price Chart with Trade Markers             │
├───────────────────────────┬─────────────────────────────┤
│    MAE/MFE Scatter        │    Duration vs P/L          │
├───────────────────────────┼─────────────────────────────┤
│    Returns Distribution   │    Time-of-Day Performance  │
└───────────────────────────┴─────────────────────────────┘
```

### 6.3 Risk Dashboard

```
┌─────────────────────────────────────────────────────────┐
│           Monte Carlo Equity Fan (1000 paths)           │
├───────────────────────────┬─────────────────────────────┤
│   Drawdown Distribution   │   Rolling Sharpe (90-day)   │
├───────────────────────────┼─────────────────────────────┤
│   VaR/CVaR Metrics        │   Risk/Reward Scatter       │
└───────────────────────────┴─────────────────────────────┘
```

---

## 7. Implementation Priorities for TRADE

### 7.1 Current State

We have:
- Candlestick chart with lightweight-charts
- Basic equity curve
- Metrics summary cards
- Trade list (partial)

### 7.2 High Priority Additions

| Feature | Effort | Impact | Data Available? |
|---------|--------|--------|-----------------|
| Drawdown overlay on equity | Low | High | Yes (equity_curve) |
| Trade markers on chart | Medium | High | Yes (trades.jsonl) |
| PnL Calendar | Medium | High | Yes (trades have timestamps) |
| MAE/MFE scatter | Low | High | Yes (in BacktestMetrics) |

### 7.3 Medium Priority

| Feature | Effort | Impact | Data Available? |
|---------|--------|--------|-----------------|
| Monthly returns heatmap | Low | Medium | Derivable |
| Time-of-day analysis | Medium | Medium | Yes (trade timestamps) |
| Duration vs P/L scatter | Low | Medium | Yes (trade data) |
| Rolling metrics chart | Medium | Medium | Derivable |

### 7.4 Lower Priority (Future)

| Feature | Effort | Impact | Notes |
|---------|--------|--------|-------|
| Monte Carlo simulation | High | High | Requires compute |
| Risk/Reward scatter | Medium | Medium | Multi-strategy comparison |
| Win/Loss streak viz | Low | Low | Nice to have |

---

## 8. Technical Recommendations

### 8.1 Charting Libraries

| Library | Pros | Cons | Use For |
|---------|------|------|---------|
| Lightweight Charts | Fast, TradingView look | Limited chart types | OHLCV, equity |
| Plotly | Interactive, many types | Heavier | Scatter, heatmaps |
| D3.js | Ultimate flexibility | Complex | Custom visualizations |
| Chart.js | Simple, lightweight | Less financial focus | Basic charts |

### 8.2 Color Scheme

```css
/* Profit/Loss */
--profit: #26a69a;      /* Green */
--profit-light: #b2dfdb;
--loss: #ef5350;        /* Red */
--loss-light: #ffcdd2;

/* Neutral */
--neutral: #78909c;
--background: #1e222d;
--card: #262932;
```

### 8.3 Interactivity Patterns

1. **Linked Charts** - hover on equity highlights trade on price chart
2. **Filter Propagation** - filter by date affects all charts
3. **Drill-Down** - click monthly cell → show daily breakdown
4. **Tooltips** - rich hover information on all data points

---

---

## 9. Organizing Backtest Results

### 9.1 Folder Structure for Artifacts

A well-organized artifact structure enables efficient comparison and retrieval:

```
backtests/
├── _index.jsonl                    # Master index of all runs
├── {category}/                     # e.g., _validation, production, research
│   └── {play_id}/                  # Strategy identifier
│       └── {symbol}/               # Trading pair
│           └── {run_id}/           # Unique run identifier
│               ├── manifest.json   # Run metadata
│               ├── config.json     # Full configuration snapshot
│               ├── trades.jsonl    # Trade-by-trade log
│               ├── equity.jsonl    # Equity curve data
│               ├── metrics.json    # Summary statistics
│               ├── ohlcv.parquet   # Price data used
│               └── snapshots/      # Optional per-bar snapshots
```

**Our Current Structure:**
```
backtests/_validation/I_001_ema/ETHUSDT/e519c964cc91/
```

### 9.2 Run Index & Comparison

**Master Index Schema** (`_index.jsonl`):
```json
{
  "run_id": "e519c964cc91",
  "play_id": "I_001_ema",
  "symbol": "ETHUSDT",
  "tf_exec": "1h",
  "window_start": "2026-01-01",
  "window_end": "2026-01-05",
  "created_at": "2026-01-06T16:19:54Z",
  "trades_count": 8,
  "net_pnl_usdt": 1002.16,
  "sharpe": 11.32,
  "max_drawdown_pct": 4.8,
  "artifact_path": "backtests/_validation/I_001_ema/ETHUSDT/e519c964cc91"
}
```

### 9.3 Strategy Comparison Features

From [Option Alpha](https://optionalpha.com/backtester):
> "Spin up new variations to view side-by-side and see how different variables, trade management, or entry/exit timing impacts performance."

**Comparison Dashboard Elements:**
1. **Side-by-Side Metrics Table**
   ```
   | Metric      | V1 (EMA 20) | V2 (EMA 50) | V3 (EMA 100) |
   |-------------|-------------|-------------|--------------|
   | Net P/L     | +$1,002     | +$856       | +$1,234      |
   | Win Rate    | 50%         | 45%         | 55%          |
   | Max DD      | 4.8%        | 6.2%        | 3.9%         |
   | Sharpe      | 11.32       | 8.45        | 14.21        |
   ```

2. **Overlaid Equity Curves** - Multiple strategies on same chart
3. **Parameter Sensitivity Heatmap** - 2D grid showing metric vs. two parameters
4. **Radar/Spider Chart** - Compare multiple metrics at once

### 9.4 Heatmap for Parameter Optimization

From [Backtesting.py](https://kernc.github.io/backtesting.py/):
> "Test hundreds of strategy variants in mere seconds, resulting in heatmaps you can interpret at a glance."

```
           SL: 1%   SL: 2%   SL: 3%   SL: 4%
TP: 2%    [12.3]   [15.1]   [11.2]   [8.4]
TP: 4%    [18.2]   [21.5]   [19.8]   [14.6]
TP: 6%    [14.1]   [17.3]   [22.1]   [18.9]
TP: 8%    [10.5]   [13.2]   [16.4]   [19.2]

Color: Sharpe ratio (green = higher)
```

---

## 10. Multi-Timeframe (MTF) Visualization

### 10.1 The MTF Challenge

Multi-timeframe strategies use:
- **HTF (Higher Timeframe)**: Trend direction, major levels (4H, 1D)
- **MTF (Mid Timeframe)**: Trade bias, structure (1H, 2H)
- **LTF/Exec (Lower Timeframe)**: Entry timing, execution (15m, 5m)

The visualization challenge: **How to show context from multiple timeframes while maintaining clarity?**

### 10.2 Layout Options

**Option A: Split-Screen Multi-Chart**

From [TradingView](https://www.tradingview.com/support/solutions/43000629990-leveraging-multi-chart-layouts-in-your-analysis/):
> "Display the same ticker on different timeframes by enabling Symbol sync and disabling Interval sync."

```
┌─────────────────────────────────────────────────────────┐
│                    HTF (4H) Chart                       │
│  [Trend context, major S/R levels, structure]           │
├─────────────────────────┬───────────────────────────────┤
│      MTF (1H) Chart     │       LTF (15m) Chart         │
│  [Trade setup context]  │  [Entry/exit execution]       │
└─────────────────────────┴───────────────────────────────┘
```

**Option B: Overlay HTF on LTF**

Use the [Multi-Time Period Charts indicator](https://www.tradingview.com/support/solutions/43000502591-multi-time-period-charts-indicator/):
> "Displays data from higher-timeframe bars directly on the chart with color-coded boxes representing HTF ranges."

```
LTF (15m) candlesticks
  │
  │  ╔═══════════════╗  ← HTF (4H) bar range box
  │  ║ ░░░▓▓▓░░░░░░░ ║
  │  ║ ░░░░░░▓▓▓░░░░ ║  ← Each 15m candle inside
  │  ║ ░░▓▓▓░░░░░░░░ ║
  │  ╚═══════════════╝
```

**Option C: Synchronized Panels**

From [TradingView](https://www.tradingview.com/support/solutions/43000670346-how-to-synchronize-the-date-range-on-multichart/):
> "Enable Date range sync - scrolling one chart synchronizes all others."

Features:
- Crosshair sync across all timeframes
- Date range sync (zoom together)
- Drawing sync (trendlines appear on all)

### 10.3 MTF Indicator Visualization

**Forward-Fill Representation:**
Show when HTF values update vs. stay constant:

```
Exec bars (15m):  |  1  |  2  |  3  |  4  |  5  |  6  |  7  |  8  |
                  ├─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
HTF EMA (4H):     │ 100 │ 100 │ 100 │ 100 │ 101 │ 101 │ 101 │ 101 │
                  └──── forward-fill ────┘ └──── forward-fill ────┘
                                         ↑
                                    HTF bar closed
```

**Visual Encoding:**
- Solid line when HTF bar closes (real update)
- Dashed/faded line during forward-fill period
- Vertical marker when HTF closes

### 10.4 Structure Visualization Across TFs

For market structures (swing highs/lows, zones), show hierarchy:

```
HTF (4H) Swing High ─────────────────────────────────
                    ╲
                     ╲  MTF (1H) Swing High ─────────
                      ╲                     ╲
                       ╲                     ╲  LTF Entry
                        ╲____________________╲____▼____
```

**Color Coding by TF:**
```css
--htf-color: #ff9800;   /* Orange - major levels */
--mtf-color: #2196f3;   /* Blue - intermediate */
--ltf-color: #4caf50;   /* Green - execution */
```

### 10.5 MTF Trade Context Display

When showing a trade, include the HTF context that justified it:

```
┌─────────────────────────────────────────────────────────┐
│ TRADE #7: LONG ETHUSDT                                  │
├─────────────────────────────────────────────────────────┤
│ HTF Context (4H):                                       │
│   Trend: BULLISH | EMA: Above | Structure: Higher High  │
├─────────────────────────────────────────────────────────┤
│ MTF Setup (1H):                                         │
│   RSI: 45 (neutral) | Near support zone                 │
├─────────────────────────────────────────────────────────┤
│ Entry (15m):                                            │
│   Signal: EMA crossover | Price: $3,421.50              │
│   Stop: $3,380 (1.2%) | Target: $3,505 (2.4%)          │
└─────────────────────────────────────────────────────────┘
```

### 10.6 Synchronized Bar Replay

From [TradingView Blog](https://www.tradingview.com/blog/en/synchronized-bar-replay-45933/):
> "Synchronously run Bar Replay on all charts of the layout and track dynamics at different timeframes at one point in time."

**Implementation:**
- Play button advances all TF charts together
- Time cursor shows same moment across all charts
- Indicators update in sync
- Useful for walk-forward analysis

### 10.7 Implementation for TRADE

**Current State:**
- We have `tf_mapping` with htf/mtf/ltf roles
- FeedStores exist for each timeframe
- Forward-fill semantics implemented

**Visualization Additions:**

1. **TF Context Panel** (sidebar):
   ```
   ┌─────────────────┐
   │ HTF (4H)        │
   │ EMA: 3,450 ↑    │
   │ Trend: BULL     │
   ├─────────────────┤
   │ MTF (1H)        │
   │ RSI: 58         │
   │ Near: Resistance│
   ├─────────────────┤
   │ Exec (15m)      │
   │ Signal: LONG    │
   └─────────────────┘
   ```

2. **HTF Level Overlay** on exec chart:
   - Draw HTF swing levels as horizontal lines
   - Show HTF zones as shaded rectangles
   - Label with TF source

3. **TF Bar Boundaries**:
   - Vertical dotted lines when HTF/MTF bars close
   - Helps understand when values update

---

## 11. Implementation Roadmap

### Phase 1: Foundation (Current)
- [x] Basic candlestick chart
- [x] Equity curve
- [x] Metrics cards
- [x] Run list

### Phase 2: Trade Analysis
- [ ] Trade markers on price chart
- [ ] Drawdown overlay on equity
- [ ] MAE/MFE scatter plots
- [ ] Trade list with details

### Phase 3: Time Analysis
- [ ] PnL calendar heatmap
- [ ] Monthly returns heatmap
- [ ] Time-of-day performance
- [ ] Duration vs P/L scatter

### Phase 4: Comparison & MTF
- [ ] Side-by-side run comparison
- [ ] Parameter sensitivity heatmap
- [ ] MTF context panel
- [ ] HTF level overlay

### Phase 5: Advanced Risk
- [ ] Monte Carlo simulation
- [ ] Rolling metrics charts
- [ ] Risk/Reward scatter
- [ ] Confidence bands

---

## Sources

- [QuantConnect Backtest Analysis](https://www.quantconnect.com/docs/v2/research-environment/meta-analysis/backtest-analysis)
- [FX Replay - Interpreting Backtest Results](https://www.fxreplay.com/learn/how-to-interpret-backtest-results-a-traders-guide-to-smarter-strategy-decisions)
- [TradesViz - Advanced Stats](https://www.tradesviz.com/blog/advanced-stats/)
- [TradesViz - MFE/MAE Charts](https://www.tradesviz.com/blog/mfe-mae-charts/)
- [TradesViz - PnL Calendar](https://www.tradesviz.com/pnl-calendar/)
- [Tradervue - Trading Analysis](https://www.tradervue.com/site/trading-analysis)
- [TradingView Lightweight Charts](https://www.tradingview.com/lightweight-charts/)
- [Jesse-Research GitHub](https://github.com/deemzie/jesse-research)
- [PyQuantLab - Equity Curve + Drawdown](https://pyquantlab.medium.com/equity-curve-max-drawdown-on-one-chart-with-matplotlib-1f6a40a8ac99)
- [StrategyQuant - Monte Carlo Analysis](https://strategyquant.com/blog/what-is-monte-carlo-analysis-and-why-you-should-use-it/)
- [HowToTrade - Monte Carlo Simulator](https://howtotrade.com/trading-tools/monte-carlo-simulation/)
- [Stock Rover - Monthly Returns Heatmap](https://www.stockrover.com/help/analytics/monthly-returns-heatmap/)
- [TradingDiaryPro - MAE/MFE Explained](https://www.tradingdiarypro.com/mae-mfe-explained/)
- [Trademetria - MAE/MFE Guide](https://trademetria.com/blog/understanding-mae-and-mfe-metrics-a-guide-for-traders/)
