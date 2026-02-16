# Market Sentiment Tracker -- Brainstorm & Design

> **Date**: 2026-02-15
> **Status**: Brainstorm / Future Feature
> **Scope**: Sentiment tracker only. Play selection / agent-based rotation is a separate future feature that will consume this tracker's output.
> **Goal**: As data streams in, maintain a real-time view of "where the market has been and where it's likely going" -- a composite market state that can later drive play selection.

---

## 1. What We Already Have

### 1.1 Indicators That Feed Regime Detection (44 Built, All O(1) Incremental)

#### Trend Indicators (14) -- Primary Regime Signals

| # | Indicator | Key Outputs | Regime Relevance |
|---|-----------|-------------|------------------|
| 1 | `ema` | value | Trend direction via crosses, slope |
| 2 | `sma` | value | Baseline trend reference |
| 3 | `wma` | value | Weighted trend, responsive |
| 4 | `dema` | value | Reduced lag trend following |
| 5 | `tema` | value | Triple-smoothed, minimal lag |
| 6 | `trima` | value | Triangular smoothed trend |
| 7 | `zlma` | value | Zero-lag trend detection |
| 8 | `kama` | value | Adapts smoothing to noise (efficiency ratio built in) |
| 9 | `alma` | value | Gaussian-weighted trend |
| 10 | `linreg` | value | Linear regression fit at endpoint |
| 11 | `supertrend` | trend, direction (1/-1), long, short | **DIRECT regime signal**: direction flips = regime change |
| 12 | `psar` | long, short, af, reversal | **DIRECT regime signal**: reversal detection |
| 13 | `aroon` | up, down, osc | **Strong regime signal**: osc polarity = trend regime, magnitude = strength |
| 14 | `donchian` | lower, middle, upper | Channel width indicates range vs breakout |

#### Momentum/Oscillator Indicators (17) -- Overbought/Oversold + Trend Strength

| # | Indicator | Key Outputs | Regime Relevance |
|---|-----------|-------------|------------------|
| 15 | `rsi` | value (0-100) | **Key regime input**: extreme = reversal, 40-60 = ranging |
| 16 | `cci` | value | Momentum regime, extended moves |
| 17 | `willr` | value (-100 to 0) | Overbought/oversold |
| 18 | `cmo` | value (-100 to 100) | Directional momentum strength |
| 19 | `mfi` | value (0-100) | Volume-weighted RSI, money flow regime |
| 20 | `uo` | value | Multi-timeframe momentum composite |
| 21 | `roc` | value | Price velocity, momentum magnitude |
| 22 | `mom` | value | Raw price momentum |
| 23 | `stoch` | k, d | Mean reversion signal, overbought/oversold |
| 24 | `stochrsi` | k, d | RSI extremes detection |
| 25 | `macd` | macd, signal, histogram | **Key regime input**: histogram polarity = momentum regime |
| 26 | `ppo` | ppo, signal, histogram | Percentage-based MACD, cross-asset comparable |
| 27 | `trix` | trix, signal | Triple-smoothed momentum rate |
| 28 | `tsi` | tsi, signal | Double-smoothed momentum, trend + strength |
| 29 | `fisher` | fisher, signal | Gaussian-normalized price position, extremes |
| 30 | `kvo` | kvo, signal | Volume trend momentum |
| 31 | `adx` | adx, dmp, dmn, adxr | **Critical regime input**: ADX > 25 trending, < 20 ranging |

#### Volatility Indicators (6) -- Regime State via Expansion/Contraction

| # | Indicator | Key Outputs | Regime Relevance |
|---|-----------|-------------|------------------|
| 32 | `atr` | value | **Core volatility measure**: expanding = trending, contracting = ranging |
| 33 | `natr` | value | Cross-asset comparable volatility |
| 34 | `bbands` | lower, middle, upper, bandwidth, percent_b | **Key regime inputs**: bandwidth = vol regime, %B = price position |
| 35 | `kc` | lower, basis, upper | Keltner width = volatility regime |
| 36 | `squeeze` | sqz, on, off, no_sqz | **DIRECT regime signal**: squeeze on/off = compression/expansion |
| 37 | `vortex` | vip, vim | Directional trend strength |

#### Volume Indicators (4) + Price Transforms (3)

| # | Indicator | Key Outputs | Regime Relevance |
|---|-----------|-------------|------------------|
| 38 | `obv` | value | Volume trend confirms price trend |
| 39 | `cmf` | value | Money flow direction |
| 40 | `vwap` | value | Institutional reference level |
| 41 | `anchored_vwap` | value, bars_since_anchor | Structure-anchored fair value |
| 42 | `ohlc4` | value | Typical price |
| 43 | `midprice` | value | High/low midpoint over period |
| 44 | `dm` | dmp, dmn | Directional movement components |

#### Top 10 Most Useful for Regime Classification

1. **ADX** -- adx value: >25 trending, <20 ranging, >40 strong
2. **BBands bandwidth** -- compression/expansion cycles
3. **Squeeze on/off** -- direct volatility regime boolean
4. **SuperTrend direction** -- binary trend regime
5. **RSI** -- extreme zones, 40-60 = indecision
6. **MACD histogram** -- momentum regime polarity
7. **ATR/NATR** -- volatility magnitude
8. **Aroon oscillator** -- trend strength and direction
9. **KAMA** -- built-in efficiency ratio = noise detection
10. **Trend structure direction** -- structure-level classification

### 1.2 Structure Detectors That Classify Market State (7 Built)

| # | Type | Key Outputs | Market State Info |
|---|------|------------|-------------------|
| 1 | **swing** | high/low levels, pair_direction, significance | Pivot detection, market rhythm |
| 2 | **trend** | direction (1/-1/0), strength (0-2), wave_count, bars_in_trend | **DIRECT regime**: uptrend/downtrend/ranging with strength |
| 3 | **market_structure** | bias (1/-1/0), bos_this_bar, choch_this_bar | **DIRECT regime change**: BOS = continuation, CHoCH = reversal |
| 4 | **fibonacci** | level values, anchor_direction | Key S/R levels, retracement depth |
| 5 | **zone** | state (active/broken), upper, lower | Demand/supply zone lifecycle |
| 6 | **derived_zone** | K zone slots, touch tracking, active_count | Multi-zone interaction map |
| 7 | **rolling_window** | value (min or max over N bars) | Price range extremes |

Notable: `TrendState` enum in `src/structures/types.py` has a comment: "BULL/BEAR are reserved for future sentiment/regime layer" -- a placeholder already exists.

### 1.3 Data Pipeline (Already Built)

- Multi-TF candle processing (low_tf / med_tf / high_tf) via WebSocket
- `RealtimeState` manages bar buffers per symbol per TF
- `LiveRunner` processes candles through engine pipeline
- Bybit WebSocket connection already established for kline data
- DSL supports `cases_when` (conditional logic), `holds_for` (persistence), `metadata` (capture at entry)

### 1.4 Risk Management -- No Market-Wide Awareness

`GlobalRisk` currently checks account/position metrics only. No volatility-based sizing, no regime-based risk modulation, no correlation tracking. The `RiskVeto` framework is the right shape to add regime-based vetoes (e.g., `ADVERSE_REGIME`, `HIGH_VOLATILITY_REGIME`).

### 1.5 What Does NOT Exist

- No composite regime classifier combining multiple signals
- No regime state machine with transitions + hysteresis
- No external data integration (funding rate, OI, liquidations, etc.)
- No sentiment scoring system
- No regime persistence / duration tracking
- No order book imbalance computation

---

## 2. Architecture Overview

```
                    +----------------------------------+
                    |     MarketSentimentTracker        |
                    |                                  |
                    |  Composite Score: -1.0 to +1.0   |
                    |  Regime: trending/ranging/vol/... |
                    |  Confidence: 0.0 to 1.0          |
                    |  Duration: N bars in regime       |
                    +----------------------------------+
                           /          |          \
                          /           |           \
              +-----------+   +-------+-------+   +------------+
              | Price-     |   | Exchange      |   | External   |
              | Derived    |   | Sentiment     |   | Sentiment  |
              | (Tier 0)   |   | (Tier 1)      |   | (Tier 2)   |
              +-----------+   +---------------+   +------------+
              | ATR %rank  |   | Funding rate  |   | Fear&Greed |
              | ADX trend  |   | OI delta      |   | On-chain   |
              | BBands BW  |   | L/S ratio     |   | Social     |
              | Squeeze    |   | Liquidations  |   | BTC dom    |
              | SuperTrend |   | Order book    |   |            |
              | MACD hist  |   | imbalance     |   |            |
              | trend.dir  |   | Volume mom    |   |            |
              | ms.bias    |   |               |   |            |
              +-----------+   +---------------+   +------------+
                    |               |                    |
              Already built    New: Bybit WS/REST     New: HTTP APIs
              (indicators +    (free, no auth)        (mostly free)
              structures)
```

### Three Tiers of Sentiment Data

**Tier 0 -- Price-Derived (already built, zero additional cost)**
Computed from existing indicators and structures on every candle close. Available immediately with no new infrastructure.

**Tier 1 -- Exchange Sentiment (free, low effort)**
Data from Bybit's public API. Funding rates, open interest, long/short ratios, liquidations, order book depth. All free, most available via WebSocket we already connect to.

**Tier 2 -- External Sentiment (free/cheap, medium effort)**
Fear & Greed Index (free daily), on-chain metrics (Glassnode free tier), social sentiment (limited free). Lower priority, daily granularity mostly.

---

## 3. Regime Classification

### 3.1 Market Regimes (Discrete States)

| Regime | Description | Key Signals |
|--------|-------------|-------------|
| `TRENDING_UP` | Strong uptrend with momentum | ADX>25, trend.direction=1, SuperTrend bullish, MACD hist>0 |
| `TRENDING_DOWN` | Strong downtrend with momentum | ADX>25, trend.direction=-1, SuperTrend bearish, MACD hist<0 |
| `RANGING` | Sideways, no clear direction | ADX<20, trend.direction=0, RSI 40-60, narrow BBands |
| `HIGH_VOLATILITY` | Extreme volatility, any direction | ATR >90th percentile, BBands expanding, liquidation spike |
| `SQUEEZE` | Compression before breakout | Squeeze.on=True, BBands inside Keltner, declining ATR |
| `BREAKOUT` | Breaking out of compression | Squeeze fired, volume spike, BOS detected |
| `CAPITULATION` | Panic selling / liquidation cascade | OI collapsing, massive liquidations, extreme Fear&Greed |

### 3.2 Regime Detection: Two-Layer Approach

**Layer 1 -- Rule-Based (fast, every candle, O(1))**
Uses existing indicators. Always running. Produces a "fast regime" classification.

```
Rules (evaluated in order, first match wins):
1. IF liquidation_volume > 3x_avg AND OI_dropping > 5%/hr  -> CAPITULATION
2. IF squeeze.on = True                                      -> SQUEEZE
3. IF squeeze_just_fired AND volume > 2x_avg                 -> BREAKOUT
4. IF ATR_percentile > 90                                    -> HIGH_VOLATILITY
5. IF ADX > 25 AND trend.direction = 1                       -> TRENDING_UP
6. IF ADX > 25 AND trend.direction = -1                      -> TRENDING_DOWN
7. ELSE                                                      -> RANGING
```

**Layer 2 -- Statistical (slower, periodic, richer) -- OPTIONAL**
HMM trained on rolling window of features. Produces regime probabilities. Updated every 4h or daily.

- Features: log returns, realized volatility, volume ratio, funding rate, OI change rate
- States: 2-4 (selected via BIC). Mapped to regime labels post-training
- Library: `hmmlearn` (`pip install hmmlearn`)
- Layer 2 is optional for Phase 1 -- Layer 1 alone is functional

### 3.3 Regime Transitions + Hysteresis

To avoid regime flickering:
- **Confirmation bars**: Regime only changes after N bars (configurable, default 3) confirm the new state
- **Transition cooldown**: Minimum bars between regime changes (default 5)
- **Confidence threshold**: Regime only confirmed when composite score > threshold

```
State machine:
  CURRENT_REGIME --(N bars confirm new regime)--> NEW_REGIME
                 --(< N bars, signal fades)----> CURRENT_REGIME (no change)
```

### 3.4 Algorithm Comparison

| Algorithm | Complexity | Temporal? | Multi-Feature? | Incremental? | Training Data | Best For |
|-----------|-----------|-----------|----------------|-------------|---------------|----------|
| Rule-based (ATR/ADX) | O(1) | No | No | Yes | None | Fast always-on classification |
| K-Means | O(N) | No | Yes | No | 200+ bars | Quick clustering |
| GMM | O(N) | No | Yes | No | 200+ bars | Soft regime membership |
| HMM | O(N*K^2) | Yes | Yes | No | 500+ bars | Gold standard regime detection |
| GARCH | O(N) | Yes | No | Partial | 500+ bars | Volatility regime specifically |

---

## 4. Sentiment Scoring

### 4.1 Composite Sentiment Score

A single number from **-1.0** (extreme bearish) to **+1.0** (extreme bullish), computed as a weighted sum of normalized sub-scores.

### 4.2 Sub-Score Components

#### A. Trend Score (weight: 0.25)
```
inputs: trend.direction, trend.strength, ADX, SuperTrend.direction, MA alignment
score: weighted average of:
  - trend.direction * trend.strength / 2    (range: -1 to +1)
  - ADX normalized: (adx - 20) / 30        (0 at ADX=20, 1 at ADX=50)
  - SuperTrend direction                    (-1 or +1)
  - MA alignment score                      (-1 to +1 based on EMA9/21/50 order)
```

#### B. Momentum Score (weight: 0.20)
```
inputs: RSI, MACD histogram, ROC, MOM
score: weighted average of:
  - RSI normalized: (rsi - 50) / 50         (-1 to +1)
  - MACD histogram sign * min(1, |hist| / atr)
  - ROC sign * min(1, |roc| / threshold)
```

#### C. Volatility Score (weight: 0.15)
```
inputs: ATR percentile, BBands bandwidth, NATR
score:
  - ATR_percentile_rank                     (0 to 1, higher = more volatile)
  - mapped to sentiment: low vol = neutral, high vol = slightly bearish (uncertainty)
  - NOTE: This is directionally neutral -- modulates confidence, not direction
```

#### D. Volume/Flow Score (weight: 0.15)
```
inputs: OBV trend, CMF, MFI, volume vs SMA
score:
  - CMF value                               (-1 to +1)
  - MFI normalized: (mfi - 50) / 50         (-1 to +1)
  - Volume momentum: vol / vol_sma20 - 1    (positive = above average)
```

#### E. Exchange Sentiment Score (weight: 0.15) -- NEW DATA
```
inputs: funding rate, OI delta, L/S ratio, liquidation volume
score: weighted average of:
  - funding_rate_zscore (positive funding = bullish leverage)
  - oi_delta_pct (rising OI + rising price = bullish)
  - ls_ratio_deviation: (ratio - 0.5) * 2   (-1 to +1)
  - liquidation_pressure: net long_liq - short_liq (normalized)
```

#### F. Macro Sentiment Score (weight: 0.10) -- NEW DATA
```
inputs: Fear & Greed Index, BTC dominance trend (if available)
score:
  - fng_normalized: (fng - 50) / 50         (-1 to +1)
  - Updated daily (stale between updates, that's OK for macro overlay)
```

### 4.3 Final Composite
```
sentiment = (
    0.25 * trend_score +
    0.20 * momentum_score +
    0.15 * volatility_modifier +
    0.15 * volume_flow_score +
    0.15 * exchange_sentiment +
    0.10 * macro_sentiment
)

confidence = 1.0 - volatility_penalty  # High vol reduces confidence
```

---

## 5. Data Sources & Integration

### 5.1 Bybit V5 API -- Exchange Data (Free, Real-Time)

All endpoints are **public** (no auth required) and **free** with standard rate limits. WebSocket requests are NOT counted against rate limits.

| Data | Endpoint | Method | Update Freq | Integration |
|------|----------|--------|-------------|-------------|
| **Funding Rate** | `/v5/market/tickers` | WS `tickers.{symbol}` | Real-time push | Add to existing WS subscription |
| **Open Interest** | `/v5/market/tickers` | WS `tickers.{symbol}` | Real-time push | Same ticker stream |
| **Long/Short Ratio** | `/v5/market/account-ratio` | REST GET, poll every 5min | 5min intervals | New REST poller |
| **Liquidations** | WS `allLiquidation` | WS Subscribe | Real-time push | New WS topic subscription |
| **Order Book** | WS `orderbook.50.{symbol}` | WS Subscribe | Real-time push | New WS topic (compute OBI) |
| **24h Volume** | `/v5/market/tickers` | WS `tickers.{symbol}` | Real-time push | Already in ticker stream |
| **Funding History** | `/v5/market/funding/history` | REST GET | Every 8h | For historical backtesting |
| **OI History** | `/v5/market/open-interest` | REST GET | 5min-1d intervals | For historical backtesting |

**Key insight**: The `tickers.{symbol}` WebSocket topic gives us funding rate, OI, volume, and bid/ask in ONE stream. We already connect to Bybit WS for kline data, so adding this topic is trivial.

### 5.2 External APIs (Free, Daily/Periodic)

| Data | API | Cost | Update Freq | Integration |
|------|-----|------|-------------|-------------|
| Fear & Greed | `https://api.alternative.me/fng/` | Free forever | Daily (cached 5min) | HTTP GET on startup + daily refresh |
| Stablecoin Supply | DeFiLlama `https://api.llama.fi/` | Free, no key | Near real-time | HTTP GET periodic |
| BTC Dominance | CoinGecko / CoinMarketCap | Free tier | Every 5min | HTTP GET periodic |

**Fear & Greed Index details**: Scale 0-100. Measures: Volatility (25%), Market Momentum/Volume (25%), Social Media (15%), Surveys (15%), Bitcoin Dominance (10%), Google Trends (10%). Python wrapper: `pip install fear-and-greed-crypto`.

### 5.3 Optional Paid Sources (Future)

| Data | API | Cost | Value |
|------|-----|------|-------|
| SOPR, Exchange Flows | Glassnode | Free tier (daily, 1000 calls/month) | On-chain fundamentals |
| Social Volume, Dev Activity | Santiment | Limited free (GraphQL) | Social sentiment |
| Comprehensive Liquidation | CoinGlass | $29/mo+ | Better liquidation data |
| Social Intelligence | LunarCrush | Paid API | Galaxy Score, AltRank |
| Exchange Flows | CryptoQuant | $29/mo+ | Taker buy/sell, exchange inflows |

### 5.4 Data Source Priority

| Priority | Source | Cost | Signal Type | Latency | Effort |
|----------|--------|------|-------------|---------|--------|
| **P0** | Bybit tickers WS (funding, OI, volume) | Free | Derivatives sentiment | Real-time | Low |
| **P0** | Bybit orderbook WS (OBI) | Free | Microstructure | Real-time | Low |
| **P0** | Bybit long/short ratio REST | Free | Positioning | 5min+ | Low |
| **P0** | Bybit liquidation WS | Free | Leverage stress | Real-time | Low |
| **P1** | Fear & Greed Index | Free | Macro sentiment | Daily | Trivial |
| **P2** | Glassnode free tier | Free | On-chain fundamentals | Daily | Medium |
| **P2** | DeFiLlama stablecoin supply | Free | Liquidity/flows | Near real-time | Low |
| **P3** | Santiment social | Limited free | Social sentiment | Varies | Medium |

---

## 6. Specific Metrics & Interpretation

### 6.1 Funding Rate Signals

| Signal | Interpretation | Regime Implication |
|--------|---------------|-------------------|
| Positive & rising | Longs paying shorts, bullish leverage building | Trend continuation if OI rising; reversal risk if extreme |
| Negative & falling | Shorts paying longs, bearish leverage | Bear continuation; squeeze risk if extreme |
| Extreme positive (>0.1%) | Overleveraged longs | High reversal probability |
| Extreme negative (<-0.05%) | Overleveraged shorts | Short squeeze incoming |
| Flip from + to - | Sentiment shift | Possible regime change |

Research: Funding rates are **trailing** for price but **leading** for volatility. Prolonged high funding precedes volatility expansion.

### 6.2 Open Interest Signals

| Signal | Interpretation |
|--------|---------------|
| Rising OI + rising price | Strong trend, new money entering long |
| Rising OI + falling price | Strong bear trend, new shorts entering |
| Falling OI + rising price | Short covering rally (weak) |
| Falling OI + falling price | Long liquidation / capitulation |
| OI spike then collapse | Liquidation cascade event |

### 6.3 Long/Short Ratio Signals

| Signal | Interpretation |
|--------|---------------|
| L/S > 0.60 | Crowded long -- contrarian bearish signal |
| L/S < 0.40 | Crowded short -- contrarian bullish signal |
| L/S rapidly shifting | Positioning flux, high uncertainty |
| L/S stable near 0.50 | Balanced positioning, neutral |

### 6.4 Liquidation Cascade Detection

| Signal | Interpretation |
|--------|---------------|
| Liquidation volume > 3x rolling 1h avg | Cascade in progress |
| Long liquidations > 80% of total | Long squeeze |
| Short liquidations > 80% of total | Short squeeze |
| OI dropping > 10% in 1h with liquidation spike | Major deleveraging event |

### 6.5 Order Book Imbalance (OBI)

**Formula**: `OBI = (sum(bid_qty) - sum(ask_qty)) / (sum(bid_qty) + sum(ask_qty))`

- Range: -1 (all asks) to +1 (all bids)
- Use top 5 depth levels, optionally distance-weighted: `weights = [1.0, 0.5, 0.25, 0.125, 0.0625]`
- Linear relationship between OBI and short-term price changes (Cont, 2014)
- **Caveat**: Spoofing is common in crypto. OBI alone is unreliable without trade-flow confirmation

### 6.6 Volume & Correlation

| Signal | Interpretation |
|--------|---------------|
| Volume > 2x 20-period SMA | High conviction move |
| Volume declining in uptrend | Exhaustion / distribution |
| BTC dominance rising > 60% | Risk-off, capital to BTC |
| BTC dominance falling, alts outperforming | Risk-on, alt season |
| Stablecoin supply contracting | Deleveraging, capital leaving crypto |

---

## 7. Regime-to-Strategy Mapping (Future Reference)

This is for the future play selector feature, but documented here for context.

| Regime | Characteristics | Strategy Type | Key Indicators |
|--------|----------------|---------------|----------------|
| **Trending Up** | ADX > 25, price above MAs, positive momentum | Momentum / trend-following | EMA cross, SuperTrend, breakouts |
| **Trending Down** | ADX > 25, price below MAs, negative momentum | Short momentum / trend-following | Death cross, breakdown plays |
| **Ranging** | ADX < 20, tight BBands, oscillating price | Mean reversion / fade extremes | RSI oversold/overbought, BBands bounce |
| **High Volatility** | ATR spike, wide BBands, high funding | Reduced size, wider stops, or sit out | ATR percentile, NATR |
| **Squeeze** | BBands squeeze, low ATR | Breakout anticipation | Squeeze indicator, Donchian breakout |
| **Capitulation** | OI dropping, high liquidations | Avoid entries, wait for reset | OI delta, liquidation volume |
| **Extreme Sentiment** | FnG > 80 or < 20, extreme funding | Contrarian signals | Fear & Greed, funding extremes |

---

## 8. Module Structure

### Proposed File Layout

```
src/sentiment/
    __init__.py
    tracker.py              # MarketSentimentTracker - main orchestrator
    regime.py               # RegimeClassifier - rule-based + optional HMM
    scores/
        __init__.py
        trend.py            # TrendScore - from existing indicators
        momentum.py         # MomentumScore - from existing indicators
        volatility.py       # VolatilityScore - from existing indicators
        volume_flow.py      # VolumeFlowScore - from existing indicators
        exchange.py         # ExchangeSentimentScore - from Bybit data
        macro.py            # MacroSentimentScore - from external APIs
    data/
        __init__.py
        bybit_sentiment.py  # Bybit REST/WS poller for funding, OI, L/S, liquidations
        orderbook.py        # Order book imbalance calculator
        external.py         # Fear & Greed, DeFiLlama, etc.
    models.py               # SentimentSnapshot, RegimeState, SentimentConfig dataclasses
    history.py              # SentimentHistory - rolling buffer for backtesting/analysis
```

### Key Dataclasses

```python
@dataclass
class SentimentSnapshot:
    """Point-in-time sentiment reading."""
    timestamp: datetime
    symbol: str

    # Composite
    sentiment_score: float          # -1.0 to +1.0
    confidence: float               # 0.0 to 1.0

    # Regime
    regime: str                     # "trending_up", "trending_down", "ranging", etc.
    regime_duration_bars: int       # How long in current regime
    regime_confidence: float        # Classifier confidence

    # Sub-scores (for transparency / debugging)
    trend_score: float
    momentum_score: float
    volatility_score: float
    volume_flow_score: float
    exchange_sentiment_score: float
    macro_sentiment_score: float

    # Raw exchange data
    funding_rate: float | None
    open_interest: float | None
    open_interest_delta_pct: float | None
    long_short_ratio: float | None
    liquidation_intensity: float | None
    order_book_imbalance: float | None
    fear_greed_index: int | None


@dataclass
class RegimeState:
    """Regime state machine with hysteresis."""
    current_regime: str
    pending_regime: str | None       # Candidate regime awaiting confirmation
    pending_bars: int                # Bars confirming pending regime
    confirmation_threshold: int      # Bars needed to confirm (default 3)
    cooldown_remaining: int          # Bars until next regime change allowed
    transition_history: list[tuple[datetime, str, str]]  # (time, from, to)


class MarketSentimentTracker:
    """Main orchestrator. One per symbol."""

    def on_candle_close(self, candle, timeframe: str) -> SentimentSnapshot:
        """Called on every candle close. Updates all price-derived scores."""

    def on_ticker_update(self, ticker_data: dict) -> None:
        """Called on Bybit ticker WS update. Updates exchange sentiment."""

    def on_liquidation(self, liq_data: dict) -> None:
        """Called on liquidation WS event."""

    def on_orderbook_update(self, orderbook: dict) -> None:
        """Called on orderbook WS update. Computes OBI."""

    def get_snapshot(self) -> SentimentSnapshot:
        """Get current sentiment state."""

    def get_regime(self) -> str:
        """Get current regime classification."""
```

---

## 9. Integration Points

### A. LiveRunner (src/engine/runners/live_runner.py)

The tracker lives alongside the engine, updated on every candle and WS event.

```
LiveRunner.__init__():
    self._sentiment_tracker = MarketSentimentTracker(symbol, config)

LiveRunner._on_kline_update():
    # Existing: process candle through engine
    # New: also update sentiment tracker
    sentiment = self._sentiment_tracker.on_candle_close(candle, timeframe)

LiveRunner._connect():
    # Existing: subscribe to kline WS topics
    # New: also subscribe to ticker, orderbook, liquidation topics
    ws.subscribe(f"tickers.{symbol}")
    ws.subscribe(f"orderbook.50.{symbol}")
    ws.subscribe("allLiquidation")
```

### B. BybitWebSocket (src/exchanges/bybit_websocket.py)

Add handlers for new WS topics (ticker, orderbook, liquidation). Route to sentiment tracker callbacks.

### C. RuntimeSnapshotView (src/backtest/runtime/snapshot_view.py)

Expose sentiment data in the snapshot so play rules can reference it via DSL:

```yaml
# Future: plays could reference sentiment
rules:
  entry:
    all:
      - ["sentiment.regime", "==", "trending_up"]
      - ["sentiment.score", ">", 0.3]
      - ["ema_9", ">", "ema_21"]
```

### D. Backtest Runner (src/engine/runners/backtest_runner.py)

For backtesting, compute historical sentiment from stored candle data + historical exchange data (if available). Price-derived scores (Tier 0) can always be computed. Exchange data (Tier 1) requires historical data storage.

### E. Dashboard / CLI Output

```
Symbol: BTCUSDT
Regime: TRENDING_UP (14 bars, confidence: 0.85)
Sentiment: +0.62 [=========>    ] Bullish
  Trend: +0.78  Momentum: +0.45  Vol: 0.35  Flow: +0.52
  Funding: +0.012%  OI: +2.3%/4h  L/S: 0.54  FnG: 72 (Greed)
```

### F. Best-Fit Integration Pattern: New Structure Type

Register `@register_structure("regime")` alongside swing, trend, etc. This automatically gets:
- Multi-TF support
- Warmup calculation
- Snapshot integration
- State persistence
- DSL access via `structure.regime.*`

---

## 10. Storage

### In-Memory (Primary)

- `SentimentSnapshot` kept in ring buffer (default 500 entries)
- `RegimeState` is a single object per symbol
- Exchange data (funding, OI, L/S) in small rolling buffers

### DuckDB (Historical, Optional)

```sql
CREATE TABLE sentiment_history (
    timestamp TIMESTAMP,
    symbol VARCHAR,
    sentiment_score FLOAT,
    regime VARCHAR,
    confidence FLOAT,
    trend_score FLOAT,
    momentum_score FLOAT,
    volatility_score FLOAT,
    volume_flow_score FLOAT,
    exchange_sentiment FLOAT,
    macro_sentiment FLOAT,
    funding_rate FLOAT,
    open_interest FLOAT,
    long_short_ratio FLOAT,
    fear_greed_index INTEGER
);
```

Written periodically (every exec TF candle close), not on every WS tick.

---

## 11. Configuration

```yaml
sentiment:
  enabled: true
  symbol: "BTCUSDT"

  # Score weights (must sum to 1.0)
  weights:
    trend: 0.25
    momentum: 0.20
    volatility: 0.15
    volume_flow: 0.15
    exchange: 0.15
    macro: 0.10

  # Regime detection
  regime:
    confirmation_bars: 3        # Bars to confirm regime change
    cooldown_bars: 5            # Min bars between changes
    adx_trend_threshold: 25     # ADX above this = trending
    adx_range_threshold: 20     # ADX below this = ranging
    atr_high_vol_percentile: 90 # ATR percentile for high-vol regime
    atr_lookback: 90            # Bars for ATR percentile

  # Exchange data (Bybit)
  exchange_data:
    funding_rate: true
    open_interest: true
    long_short_ratio: true
    long_short_poll_interval: 300  # seconds (5 min)
    liquidations: true
    orderbook_imbalance: true
    orderbook_depth: 50            # Depth levels for OBI

  # External data
  external_data:
    fear_greed: true
    fear_greed_refresh_interval: 3600  # seconds (1 hour)

  # History
  history:
    buffer_size: 500            # In-memory ring buffer
    persist_to_db: false        # Write to DuckDB
```

---

## 12. Update Frequency & Lookback Windows

### Update Frequency

| Component | Update Frequency | Trigger |
|-----------|-----------------|---------|
| OBI score | Every orderbook update (~100ms) | WS push |
| Micro sentiment (funding, OI) | Every ticker WS update | WS push |
| Short-term regime (vol/trend) | Every exec TF candle close | Candle event |
| Medium-term regime (HMM) | Every 4h or daily | Timer / candle event |
| Macro sentiment (FnG, on-chain) | Once daily | Cron / startup |
| Full regime retrain (HMM) | Weekly or on regime-change signal | Manual / scheduled |

### Lookback Windows

| Signal | Recommended Lookback | Rationale |
|--------|---------------------|-----------|
| OBI | Last 5-10 seconds (raw) | Microstructure signal, fast decay |
| Funding rate trend | Last 3-5 settlements (24-40h) | Captures directional shift |
| OI delta | Last 4-24 hours | Detects leverage buildup |
| Liquidation volume | 1h rolling window | Captures cascade events |
| Long/short ratio | 4h-24h trend | Positioning shifts slowly |
| Volatility regime (HMM) | 200-500 daily bars | Statistical training window |
| ATR percentile | 90 bars at exec TF | Rolling percentile rank |
| Fear & Greed | Current + 7-day / 30-day average | Context for current reading |

---

## 13. Implementation Phases

### Phase 1: Price-Derived Sentiment (Tier 0) -- Zero New Dependencies

**What**: Use existing indicators + structures to compute trend, momentum, volatility, and volume sub-scores. Implement regime classifier (rule-based). Add `SentimentSnapshot` and `MarketSentimentTracker`.

**Effort**: Small. All indicator values already available in the engine pipeline.

**Deliverables**:
- `src/sentiment/` module with tracker, regime, scores (price-derived only)
- `SentimentSnapshot` and `RegimeState` dataclasses
- Rule-based regime classifier using ADX, BBands, Squeeze, SuperTrend, trend structure
- Composite score from trend + momentum + volatility + volume sub-scores
- CLI output showing current sentiment/regime

### Phase 2: Bybit Exchange Sentiment (Tier 1) -- Bybit WS/REST Only

**What**: Subscribe to `tickers.{symbol}`, `orderbook.{depth}.{symbol}`, `allLiquidation` WS topics. Poll `/v5/market/account-ratio` REST for L/S ratio. Compute exchange sentiment sub-score.

**Effort**: Medium. WebSocket infrastructure exists; need new topic handlers and data models.

**Deliverables**:
- `src/sentiment/data/bybit_sentiment.py` -- WS/REST data collection
- `src/sentiment/data/orderbook.py` -- OBI computation
- `src/sentiment/scores/exchange.py` -- exchange sentiment sub-score

### Phase 3: External Data (Tier 2) -- HTTP APIs

**What**: Fear & Greed Index (daily HTTP call). Optional: DeFiLlama stablecoin supply. Wire macro sub-score into composite.

**Effort**: Small. Simple HTTP GET with caching.

**Deliverables**:
- `src/sentiment/data/external.py` -- Fear & Greed + optional APIs
- `src/sentiment/scores/macro.py` -- macro sentiment sub-score

### Phase 4: Historical Sentiment for Backtesting

**What**: Compute and store historical sentiment alongside backtest runs. Enable backtesting of sentiment-aware plays.

**Effort**: Medium. Tier 0 sentiment computable from candle data. Tier 1/2 needs historical storage.

**Deliverables**:
- Sentiment computation in `BacktestRunner` pipeline
- Optional DuckDB table for historical sentiment
- DSL access: `sentiment.regime`, `sentiment.score` in play rules

### Phase 5: Statistical Regime Detection (Optional)

**What**: Add HMM-based regime classifier. Train on rolling windows. Ensemble with rule-based Layer 1.

**Effort**: Large. New dependency (hmmlearn). Training pipeline. Feature engineering.

**Deliverables**:
- HMM training and prediction in `src/sentiment/regime.py`
- Ensemble regime output (rule-based + HMM)
- Periodic retraining logic

---

## 14. Open Questions

1. **Per-symbol or global?** Should sentiment track each symbol independently, or maintain a "market-wide" composite (e.g., BTC sentiment influences altcoin plays)?

2. **Regime vs sentiment naming?** The "regime" (trending/ranging/volatile) is related but distinct from "sentiment" (bullish/bearish). Keep both as separate fields? Current design: yes, both exposed.

3. **Backtest fidelity for exchange data?** Historical funding rates and OI are available from Bybit API. Should we store them for backtesting? Without them, backtests only have Tier 0 (price-derived) sentiment.

4. **How does sentiment surface to the user?** Options:
   - Dashboard panel (live mode)
   - Log lines per candle
   - Accessible via DSL in play rules
   - All of the above (recommended)

5. **Weight tuning?** The sub-score weights are initial guesses. Tuning mechanism vs manual adjustment?

6. **Multi-symbol correlation?** Track BTC-altcoin correlation as a regime signal? Requires data for multiple symbols simultaneously.

---

## 15. Dependencies & Libraries

### Required (Phases 1-3)
- None new. All price-derived. HTTP calls use stdlib `urllib` or existing `requests`.

### Optional (Phase 5)
- `hmmlearn` -- HMM regime detection
- `scikit-learn` -- clustering alternatives (GMM, K-Means)

---

## 16. References

### Bybit API
- [Tickers](https://bybit-exchange.github.io/docs/v5/market/tickers)
- [Funding Rate History](https://bybit-exchange.github.io/docs/v5/market/history-fund-rate)
- [Open Interest](https://bybit-exchange.github.io/docs/v5/market/open-interest)
- [Long/Short Ratio](https://bybit-exchange.github.io/docs/v5/market/long-short-ratio)
- [All Liquidation WS](https://bybit-exchange.github.io/docs/v5/websocket/public/all-liquidation)
- [Ticker WS](https://bybit-exchange.github.io/docs/v5/websocket/public/ticker)
- [Orderbook WS](https://bybit-exchange.github.io/docs/v5/websocket/public/orderbook)

### Sentiment Data
- [Alternative.me Fear & Greed API](https://alternative.me/crypto/api/)
- [Glassnode API](https://docs.glassnode.com/)
- [Santiment API (GraphQL)](https://api.santiment.net/)
- [DeFiLlama API](https://defillama.com/docs/api)
- [LunarCrush](https://lunarcrush.com/)
- [CoinGlass](https://www.coinglass.com/)

### Regime Detection Research
- [QuantStart -- HMM Regime Detection](https://www.quantstart.com/articles/market-regime-detection-using-hidden-markov-models-in-qstrader/)
- [QuantInsti -- HMM + Random Forest](https://blog.quantinsti.com/regime-adaptive-trading-python/)
- [PyQuant News -- 3 Ways Quants Detect Regimes](https://www.pyquantnews.com/the-pyquant-newsletter/3-ways-quants-detect-market-regimes-for-an-edge)
- [Macrosynergy -- Classifying Market Regimes](https://macrosynergy.com/research/classifying-market-regimes/)
- [Order Book Imbalance Price Impact (Cont, 2014)](https://towardsdatascience.com/price-impact-of-order-book-imbalance-in-cryptocurrency-markets-bf39695246f6/)
- [QuantEvolve -- Multi-Agent Evolutionary Framework (arXiv)](https://arxiv.org/html/2510.18569v1)
- [Regime-Aware RL (arXiv)](https://arxiv.org/html/2509.14385v1)
- [Multi-Timeframe Adaptive Regime Strategy](https://medium.com/@FMZQuant/multi-timeframe-adaptive-market-regime-quantitative-trading-strategy-1b16309ddabb)
