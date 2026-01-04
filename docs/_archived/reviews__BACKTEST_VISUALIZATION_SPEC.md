# Backtest Visualization Spec

> **Status**: Draft for review
> **Date**: 2026-01-03

---

## Data Sources Available

| Source | File | Key Fields |
|--------|------|------------|
| **Metrics** | `result.json` | 62-field BacktestMetrics |
| **Trades** | `trades.parquet` | entry/exit, PnL, MAE/MFE, duration, exit_reason |
| **Equity** | `equity.parquet` | timestamp, equity, drawdown, drawdown_pct |
| **Account** | `account_curve.parquet` | margin ratios, free balance, liquidation proximity |
| **Returns** | `returns.json` | daily/weekly/monthly return aggregations |

---

## Core Visualizations (Priority 1)

### 1. Equity Curve with Drawdown

**Purpose**: Primary performance view
**Data**: `equity.parquet`

**Elements**:
- Line chart: equity over time (top panel)
- Filled area: drawdown % below zero line (bottom panel)
- Markers: trade entry/exit points (optional overlay)
- Horizontal line: initial equity reference

**Questions**:
- [ ] Include trade markers on equity curve?
- [ ] Separate panels or overlaid?

---

### 2. Monthly Returns Heatmap

**Purpose**: Seasonality and consistency
**Data**: `returns.json` → `monthly_returns`

**Elements**:
- Grid: months (cols) × years (rows)
- Color scale: red (negative) → white (zero) → green (positive)
- Cell values: return %

**Questions**:
- [ ] Weekly granularity option?
- [ ] Include annual totals row?

---

### 3. Trade Distribution Histogram

**Purpose**: Win/loss magnitude distribution
**Data**: `trades.parquet` → `net_pnl` or `pnl_pct`

**Elements**:
- Histogram bins with win/loss coloring
- Vertical line: zero (break-even)
- Annotations: avg win, avg loss, expectancy

**Questions**:
- [ ] Show in USDT or % terms?
- [ ] Separate long/short distributions?

---

### 4. Key Metrics Dashboard

**Purpose**: Summary at a glance
**Data**: `result.json` → BacktestMetrics

**Elements**:
- Tiles/cards for: net_return_pct, sharpe, sortino, max_drawdown_pct, win_rate, profit_factor
- Color coding: green/red based on thresholds
- Comparison to benchmark (alpha)

**Questions**:
- [ ] Which metrics are "must show"?
- [ ] Threshold values for color coding?

---

## Extended Visualizations (Priority 2)

### 5. MAE/MFE Scatter Plot

**Purpose**: Trade quality analysis
**Data**: `trades.parquet` → `mae_pct`, `mfe_pct`

**Elements**:
- Scatter: X = MAE (adverse), Y = MFE (favorable)
- Color: winners (green) vs losers (red)
- Quadrant lines at typical stop/target levels

**Insight**: Clusters reveal if stops are too tight or targets too ambitious

---

### 6. Leverage & Margin Timeline

**Purpose**: Risk exposure over time
**Data**: `account_curve.parquet`

**Elements**:
- Line: margin ratio over time
- Shaded danger zone: below maintenance margin
- Markers: margin calls, entry rejections

---

### 7. Long vs Short Performance

**Purpose**: Directional bias analysis
**Data**: BacktestMetrics → `long_*`, `short_*` fields

**Elements**:
- Side-by-side bars: long_pnl vs short_pnl
- Win rate comparison
- Trade count comparison

---

### 8. Trade Duration Analysis

**Purpose**: Holding period patterns
**Data**: `trades.parquet` → `duration_bars`

**Elements**:
- Histogram: trade duration distribution
- Separate series: winners vs losers

**Insight**: Are losers held too long? Winners cut too short?

---

### 9. Exit Reason Breakdown

**Purpose**: How trades end
**Data**: `trades.parquet` → `exit_price_source`

**Elements**:
- Pie/donut chart: tp_level, sl_level, signal, liquidation, etc.
- Color coding by category

---

### 10. Rolling Performance Metrics

**Purpose**: Strategy stability over time
**Data**: Computed from `equity.parquet`

**Elements**:
- Rolling 30-day Sharpe
- Rolling drawdown
- Rolling win rate

---

## Technical Approach Options

### Option A: HTML Report (Recommended)

**Stack**: Python → Plotly/Altair → Static HTML

**Pros**:
- No dependencies for viewing
- Shareable single file
- Interactive (zoom, hover, tooltips)
- Works offline

**Implementation**:
```bash
backtest report <run_id> --output report.html
```

**Questions**:
- [ ] Plotly vs Altair vs other?
- [ ] Single page or multi-tab?

---

### Option B: CLI + Terminal Charts

**Stack**: Rich + plotext (or textual)

**Pros**:
- Stays in terminal
- No browser needed
- Fast iteration

**Cons**:
- Limited interactivity
- Resolution constraints
- No export/share

---

### Option C: Jupyter Integration

**Stack**: Export data → Notebook template

**Pros**:
- Full customization
- Familiar to quants
- Can add custom analysis

**Implementation**:
```bash
backtest export <run_id> --format notebook
```

---

## Proposed CLI Commands

```bash
# Generate full HTML report
python trade_cli.py backtest report <run_id>
python trade_cli.py backtest report --latest

# Quick terminal summary (existing, enhanced)
python trade_cli.py backtest results <run_id>

# Export raw data for custom viz
python trade_cli.py backtest export <run_id> --format csv|parquet|json
```

---

## Output File Structure

```
backtests/{category}/{card_id}/{symbol}/{hash}/
├── result.json
├── trades.parquet
├── equity.parquet
└── report.html          # ← NEW: generated visualization
```

---

## Implementation Phases

### Phase 1: Minimal Viable Report

| Viz | Effort | Value |
|-----|--------|-------|
| Equity + Drawdown | Medium | High |
| Metrics Dashboard | Low | High |
| Monthly Heatmap | Low | Medium |
| Trade Histogram | Low | Medium |

**New dependency**: `plotly` (BSD license, ~15MB)

### Phase 2: Extended Analytics

- MAE/MFE scatter
- Exit reason breakdown
- Long/short comparison

### Phase 3: Advanced

- Rolling metrics
- Margin timeline
- Multi-run comparison view

---

## Open Questions

1. **Library choice**: Plotly (more features) vs Altair (cleaner API)?
2. **Report trigger**: Auto-generate on backtest completion, or on-demand only?
3. **Comparison view**: Support overlaying multiple runs on same chart?
4. **Dark mode**: Match terminal aesthetic or standard light charts?
5. **Size budget**: How large is acceptable for report.html? (Plotly can be 3-5MB)

---

## Notes / Brainstorm Space

<!-- Add your thoughts here -->
