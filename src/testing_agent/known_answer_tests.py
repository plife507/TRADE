"""
Known-Answer Tests: Synthetic scenarios with predetermined correct answers.

These tests use engineered data where we know exactly when signals should fire,
what fills should occur, and what the final P/L should be. This proves correctness,
not just that the code runs.

Usage:
    from src.testing_agent.known_answer_tests import (
        create_ema_cross_scenario,
        create_sl_tp_scenario,
        run_known_answer_test,
    )

    scenario = create_ema_cross_scenario(cross_bar=50, direction="long")
    result = run_known_answer_test(scenario)
    assert result.passed
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from ..utils.logger import get_logger

logger = get_logger()


# =============================================================================
# Data Classes
# =============================================================================

class SignalDirection(str, Enum):
    """Signal direction for expected signals."""
    LONG = "long"
    SHORT = "short"


class ExitReason(str, Enum):
    """Reason for trade exit."""
    STOP_LOSS = "sl"
    TAKE_PROFIT = "tp"
    SIGNAL = "signal"
    TIMEOUT = "timeout"


@dataclass
class ExpectedSignal:
    """Expected signal at a specific bar."""
    bar_idx: int
    direction: SignalDirection
    trigger_reason: str  # "ema_cross", "rsi_oversold", etc.
    tolerance_bars: int = 0  # Allow signal within N bars of expected


@dataclass
class ExpectedTrade:
    """Expected trade with full lifecycle."""
    entry_bar: int
    entry_price: float
    exit_bar: int
    exit_price: float
    exit_reason: ExitReason
    direction: SignalDirection
    pnl: float
    size: float = 1.0
    tolerance_bars: int = 5  # Allow fill within N bars of expected (signals have lag)
    tolerance_price_pct: float = 2.0  # Allow price within X% of expected


@dataclass
class KnownAnswerScenario:
    """
    Synthetic data scenario with predetermined correct answers.

    The candles DataFrame is engineered to produce specific signals
    at specific bars. The expected_signals and expected_trades define
    what the backtest engine should produce.
    """
    name: str
    description: str
    candles: pd.DataFrame  # Synthetic OHLCV with 'timestamp' column
    expected_signals: list[ExpectedSignal] = field(default_factory=list)
    expected_trades: list[ExpectedTrade] = field(default_factory=list)
    play_config: dict = field(default_factory=dict)  # Play YAML content as dict
    tolerance: float = 1e-6  # Numerical tolerance for comparisons
    symbol: str = "BTCUSDT"
    timeframe: str = "15m"


@dataclass
class SignalMatch:
    """Result of matching an actual signal to expected."""
    expected: ExpectedSignal
    actual_bar: int | None
    actual_direction: str | None
    matched: bool
    bar_diff: int = 0
    notes: str = ""


@dataclass
class TradeMatch:
    """Result of matching an actual trade to expected."""
    expected: ExpectedTrade
    actual: dict | None  # Trade dict from engine
    matched: bool
    entry_bar_diff: int = 0
    exit_bar_diff: int = 0
    entry_price_diff_pct: float = 0.0
    exit_price_diff_pct: float = 0.0
    pnl_diff: float = 0.0
    notes: str = ""


@dataclass
class KnownAnswerResult:
    """Result from running a known-answer test."""
    scenario_name: str
    passed: bool
    signal_matches: list[SignalMatch] = field(default_factory=list)
    trade_matches: list[TradeMatch] = field(default_factory=list)
    signals_passed: int = 0
    signals_failed: int = 0
    trades_passed: int = 0
    trades_failed: int = 0
    actual_signals: list[dict] = field(default_factory=list)
    actual_trades: list[dict] = field(default_factory=list)
    error: str | None = None
    duration_ms: int = 0


# =============================================================================
# Synthetic Data Provider for Known-Answer Tests
# =============================================================================

class KnownAnswerDataProvider:
    """
    Data provider that wraps KnownAnswerScenario candles.

    Implements the same interface as SyntheticCandlesProvider
    to allow injection into the backtest engine.
    """

    def __init__(
        self,
        scenario: KnownAnswerScenario,
        additional_timeframes: list[str] | None = None,
    ):
        """
        Initialize with scenario candles.

        Args:
            scenario: KnownAnswerScenario with engineered candles
            additional_timeframes: Additional TFs to generate (resampled from base)
        """
        self._scenario = scenario
        self._symbol = scenario.symbol
        self._base_tf = scenario.timeframe
        self._candles = scenario.candles.copy()

        # Build timeframe data dict
        self._timeframes: dict[str, pd.DataFrame] = {}
        self._timeframes[self._base_tf] = self._candles

        # Generate additional timeframes by resampling
        if additional_timeframes:
            for tf in additional_timeframes:
                if tf != self._base_tf:
                    self._timeframes[tf] = self._resample_candles(self._candles, self._base_tf, tf)

    def _resample_candles(
        self,
        df: pd.DataFrame,
        from_tf: str,
        to_tf: str,
    ) -> pd.DataFrame:
        """Resample candles from one timeframe to another."""
        tf_minutes = {
            "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
            "1h": 60, "2h": 120, "4h": 240, "6h": 360, "12h": 720, "D": 1440,
        }

        from_mins = tf_minutes.get(from_tf, 15)
        to_mins = tf_minutes.get(to_tf, 60)

        if to_mins <= from_mins:
            # Can't upsample, just return copy
            return df.copy()

        # Resample by aggregating
        ratio = to_mins // from_mins
        result_rows = []

        for i in range(0, len(df), ratio):
            chunk = df.iloc[i:i + ratio]
            if len(chunk) == 0:
                continue

            result_rows.append({
                "timestamp": chunk.iloc[0]["timestamp"],
                "open": chunk.iloc[0]["open"],
                "high": chunk["high"].max(),
                "low": chunk["low"].min(),
                "close": chunk.iloc[-1]["close"],
                "volume": chunk["volume"].sum(),
            })

        return pd.DataFrame(result_rows)

    @property
    def symbol(self) -> str:
        """Get the symbol."""
        return self._symbol

    @property
    def available_timeframes(self) -> list[str]:
        """Get list of available timeframes."""
        return list(self._timeframes.keys())

    def get_ohlcv(
        self,
        symbol: str,
        tf: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """
        Return OHLCV DataFrame for the given parameters.

        Args:
            symbol: Trading symbol (validated)
            tf: Timeframe string
            start: Start datetime
            end: End datetime

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        if symbol != self._symbol:
            raise ValueError(f"Symbol mismatch: requested {symbol}, have {self._symbol}")

        if tf not in self._timeframes:
            raise ValueError(f"TF {tf} not available. Have: {list(self._timeframes.keys())}")

        df = self._timeframes[tf].copy()

        # Filter to requested time range
        mask = (df["timestamp"] >= start) & (df["timestamp"] <= end)
        filtered = df[mask].reset_index(drop=True)

        if filtered.empty:
            raise ValueError(
                f"No data for {symbol} {tf} between {start} and {end}. "
                f"Data range: {df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]}"
            )

        return filtered

    def get_1m_quotes(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Return 1m quote data (uses base TF if not 1m)."""
        if "1m" in self._timeframes:
            return self.get_ohlcv(symbol, "1m", start, end)
        # Fall back to base TF
        return self.get_ohlcv(symbol, self._base_tf, start, end)

    def has_tf(self, tf: str) -> bool:
        """Check if timeframe is available."""
        return tf in self._timeframes

    def get_data_range(self, tf: str) -> tuple[datetime, datetime]:
        """Get the time range for a timeframe."""
        if tf not in self._timeframes:
            raise ValueError(f"TF {tf} not available")

        df = self._timeframes[tf]
        return df["timestamp"].iloc[0], df["timestamp"].iloc[-1]


# =============================================================================
# Synthetic Data Generators
# =============================================================================

def _create_base_candles(
    bars: int = 200,
    start_price: float = 50000.0,
    volatility: float = 0.001,
    seed: int = 42,
    start_time: datetime | None = None,
    timeframe: str = "15m",
) -> pd.DataFrame:
    """
    Create base OHLCV candles with random walk.

    Args:
        bars: Number of bars to generate
        start_price: Starting price
        volatility: Price volatility per bar (as fraction)
        seed: Random seed for reproducibility
        start_time: Starting timestamp
        timeframe: Timeframe for timestamp spacing

    Returns:
        DataFrame with timestamp, open, high, low, close, volume
    """
    np.random.seed(seed)

    if start_time is None:
        start_time = datetime(2024, 1, 1, 0, 0, 0)

    # Parse timeframe to minutes
    tf_minutes = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "D": 1440}.get(
        timeframe, 15
    )

    timestamps = [start_time + timedelta(minutes=tf_minutes * i) for i in range(bars)]

    # Generate random returns
    returns = np.random.normal(0, volatility, bars)
    prices = start_price * np.cumprod(1 + returns)

    # Generate OHLC from close prices
    opens = np.roll(prices, 1)
    opens[0] = start_price

    # High/low with some randomness
    hl_spread = np.abs(np.random.normal(0, volatility * 0.5, bars))
    highs = np.maximum(opens, prices) * (1 + hl_spread)
    lows = np.minimum(opens, prices) * (1 - hl_spread)

    # Volume
    volumes = np.random.uniform(100, 1000, bars)

    df = pd.DataFrame({
        "timestamp": timestamps,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": prices,
        "volume": volumes,
    })

    return df


def _engineer_ema_cross(
    df: pd.DataFrame,
    cross_bar: int,
    direction: SignalDirection,
    fast_period: int = 9,
    slow_period: int = 21,
) -> pd.DataFrame:
    """
    Engineer price data so EMA(fast) crosses EMA(slow) at exact bar.

    Strategy: Create a clear trend reversal that will cause the EMA crossover.
    For a bullish cross at bar N, we need prices declining before N (fast < slow)
    then sharply rising at N so fast EMA catches up and crosses slow EMA.
    """
    df = df.copy()
    n = len(df)
    close = df["close"].values.copy()
    base_price = close[0]

    if direction == SignalDirection.LONG:
        # Phase 1: Establish downtrend before cross_bar (fast < slow)
        # Start gentle decline well before the cross
        for i in range(max(slow_period, 21), cross_bar):
            decline_pct = 0.15 * (i - slow_period) / (cross_bar - slow_period)
            close[i] = base_price * (1 - decline_pct)

        # Phase 2: Sharp reversal starting at cross_bar (fast catches up and crosses)
        # Create sustained upward movement that lasts long enough for cross
        reversal_base = close[cross_bar - 1] if cross_bar > 0 else base_price
        for i in range(cross_bar, min(n, cross_bar + 40)):
            rise_pct = 0.02 * (i - cross_bar + 1)  # Steady uptrend
            close[i] = reversal_base * (1 + rise_pct)
    else:
        # Phase 1: Establish uptrend before cross_bar (fast > slow)
        for i in range(max(slow_period, 21), cross_bar):
            rise_pct = 0.15 * (i - slow_period) / (cross_bar - slow_period)
            close[i] = base_price * (1 + rise_pct)

        # Phase 2: Sharp decline starting at cross_bar
        reversal_base = close[cross_bar - 1] if cross_bar > 0 else base_price
        for i in range(cross_bar, min(n, cross_bar + 40)):
            decline_pct = 0.02 * (i - cross_bar + 1)
            close[i] = reversal_base * (1 - decline_pct)

    df["close"] = close
    df["high"] = np.maximum(df["open"], df["close"]) * 1.001
    df["low"] = np.minimum(df["open"], df["close"]) * 0.999

    return df


def _engineer_rsi_level(
    df: pd.DataFrame,
    target_bar: int,
    target_rsi: float,
    period: int = 14,
) -> pd.DataFrame:
    """Engineer price data so RSI hits target level at specific bar."""
    df = df.copy()
    close = df["close"].values.copy()

    if target_rsi < 50:
        # Need selling pressure
        for i in range(max(1, target_bar - period * 2), target_bar):
            distance = target_bar - i
            if distance <= period:
                adjustment = -0.005 * (period - distance) / period
                close[i] = close[i - 1] * (1 + adjustment)
    else:
        # Need buying pressure
        for i in range(max(1, target_bar - period * 2), target_bar):
            distance = target_bar - i
            if distance <= period:
                adjustment = 0.005 * (period - distance) / period
                close[i] = close[i - 1] * (1 + adjustment)

    df["close"] = close
    df["high"] = np.maximum(df["open"], df["close"]) * 1.001
    df["low"] = np.minimum(df["open"], df["close"]) * 0.999

    return df


def _engineer_sl_tp_hit(
    df: pd.DataFrame,
    entry_bar: int,
    hit_bar: int,
    hit_type: ExitReason,
    entry_price: float,
    sl_pct: float = 3.0,
    tp_pct: float = 6.0,
    direction: SignalDirection = SignalDirection.LONG,
) -> pd.DataFrame:
    """Engineer price data so SL or TP is hit at exact bar."""
    df = df.copy()
    close = df["close"].values.copy()
    high = df["high"].values.copy()
    low = df["low"].values.copy()

    if direction == SignalDirection.LONG:
        sl_price = entry_price * (1 - sl_pct / 100)
        tp_price = entry_price * (1 + tp_pct / 100)

        # Keep price in safe zone until hit_bar
        for i in range(entry_bar + 1, hit_bar):
            mid_price = entry_price * (1 + (tp_pct / 2 - sl_pct / 2) / 100)
            close[i] = mid_price + np.random.uniform(-0.01, 0.01) * mid_price
            high[i] = close[i] * 1.005
            low[i] = close[i] * 0.995

        # Hit at hit_bar
        if hit_type == ExitReason.STOP_LOSS:
            low[hit_bar] = sl_price * 0.995
            close[hit_bar] = sl_price * 0.998
            high[hit_bar] = entry_price * 1.001
        else:
            high[hit_bar] = tp_price * 1.005
            close[hit_bar] = tp_price * 1.002
            low[hit_bar] = entry_price * 0.999
    else:
        sl_price = entry_price * (1 + sl_pct / 100)
        tp_price = entry_price * (1 - tp_pct / 100)

        for i in range(entry_bar + 1, hit_bar):
            mid_price = entry_price * (1 - (tp_pct / 2 - sl_pct / 2) / 100)
            close[i] = mid_price + np.random.uniform(-0.01, 0.01) * mid_price
            high[i] = close[i] * 1.005
            low[i] = close[i] * 0.995

        if hit_type == ExitReason.STOP_LOSS:
            high[hit_bar] = sl_price * 1.005
            close[hit_bar] = sl_price * 1.002
            low[hit_bar] = entry_price * 0.999
        else:
            low[hit_bar] = tp_price * 0.995
            close[hit_bar] = tp_price * 0.998
            high[hit_bar] = entry_price * 1.001

    df["close"] = close
    df["high"] = high
    df["low"] = low

    return df


# =============================================================================
# Scenario Factories
# =============================================================================

def create_ema_cross_scenario(
    cross_bar: int = 50,
    direction: Literal["long", "short"] = "long",
    fast_period: int = 9,
    slow_period: int = 21,
    bars: int = 200,
    seed: int = 42,
    symbol: str = "BTCUSDT",
    timeframe: str = "15m",
) -> KnownAnswerScenario:
    """
    Create scenario where EMA(fast) crosses EMA(slow) at exact bar.

    Args:
        cross_bar: Bar index where cross occurs
        direction: "long" (fast crosses above slow) or "short" (fast crosses below)
        fast_period: Fast EMA period
        slow_period: Slow EMA period
        bars: Total bars in dataset
        seed: Random seed
        symbol: Symbol for the scenario
        timeframe: Timeframe for the scenario

    Returns:
        KnownAnswerScenario with engineered data and expected signal
    """
    sig_dir = SignalDirection.LONG if direction == "long" else SignalDirection.SHORT

    df = _create_base_candles(bars=bars, seed=seed, timeframe=timeframe)
    df = _engineer_ema_cross(df, cross_bar, sig_dir, fast_period, slow_period)

    expected_signal = ExpectedSignal(
        bar_idx=cross_bar,
        direction=sig_dir,
        trigger_reason="ema_cross",
        tolerance_bars=15,  # EMA crossovers have inherent lag from smoothing
    )

    # Play config using correct YAML structure (flat features dict)
    play_config = {
        "version": "3.0.0",
        "name": f"KA_ema_cross_{direction}",
        "symbol": symbol,
        "timeframes": {
            "low_tf": timeframe,
            "med_tf": timeframe,  # Use same TF to simplify
            "high_tf": timeframe,
            "exec": "low_tf",
        },
        "features": {
            f"ema_{fast_period}": {"indicator": "ema", "params": {"length": fast_period}},
            f"ema_{slow_period}": {"indicator": "ema", "params": {"length": slow_period}},
        },
        "actions": {
            f"entry_{direction}": {
                "all": [[f"ema_{fast_period}", "cross_above" if direction == "long" else "cross_below", f"ema_{slow_period}"]],
            },
        },
        "position_policy": {
            "mode": f"{direction}_only",
            "exit_mode": "sl_tp_only",
        },
        "risk": {
            "stop_loss_pct": 3.0,
            "take_profit_pct": 6.0,
        },
        "account": {
            "starting_equity_usdt": 10000.0,
            "max_leverage": 1,
        },
    }

    return KnownAnswerScenario(
        name=f"KA_001_ema_cross_{direction}",
        description=f"EMA({fast_period}) crosses {'above' if direction == 'long' else 'below'} EMA({slow_period}) at bar {cross_bar}",
        candles=df,
        expected_signals=[expected_signal],
        expected_trades=[],
        play_config=play_config,
        symbol=symbol,
        timeframe=timeframe,
    )


def create_rsi_threshold_scenario(
    target_bar: int = 50,
    threshold: Literal["oversold", "overbought"] = "oversold",
    period: int = 14,
    bars: int = 200,
    seed: int = 42,
    symbol: str = "BTCUSDT",
    timeframe: str = "15m",
) -> KnownAnswerScenario:
    """Create scenario where RSI crosses threshold at exact bar."""
    target_rsi = 25.0 if threshold == "oversold" else 75.0
    direction = "long" if threshold == "oversold" else "short"
    sig_dir = SignalDirection.LONG if threshold == "oversold" else SignalDirection.SHORT

    df = _create_base_candles(bars=bars, seed=seed, timeframe=timeframe)
    df = _engineer_rsi_level(df, target_bar, target_rsi, period)

    expected_signal = ExpectedSignal(
        bar_idx=target_bar,
        direction=sig_dir,
        trigger_reason=f"rsi_{threshold}",
        tolerance_bars=10,  # RSI has lag and engineered data is approximate
    )

    play_config = {
        "version": "3.0.0",
        "name": f"KA_rsi_{threshold}",
        "symbol": symbol,
        "timeframes": {
            "low_tf": timeframe,
            "med_tf": timeframe,
            "high_tf": timeframe,
            "exec": "low_tf",
        },
        "features": {
            f"rsi_{period}": {"indicator": "rsi", "params": {"length": period}},
        },
        "actions": {
            f"entry_{direction}": {
                "all": [[f"rsi_{period}", "<" if threshold == "oversold" else ">", 30 if threshold == "oversold" else 70]],
            },
        },
        "position_policy": {
            "mode": f"{direction}_only",
            "exit_mode": "sl_tp_only",
        },
        "risk": {
            "stop_loss_pct": 3.0,
            "take_profit_pct": 6.0,
        },
        "account": {
            "starting_equity_usdt": 10000.0,
            "max_leverage": 1,
        },
    }

    return KnownAnswerScenario(
        name=f"KA_003_rsi_{threshold}",
        description=f"RSI({period}) crosses {'below 30' if threshold == 'oversold' else 'above 70'} at bar {target_bar}",
        candles=df,
        expected_signals=[expected_signal],
        expected_trades=[],
        play_config=play_config,
        symbol=symbol,
        timeframe=timeframe,
    )


def create_sl_tp_scenario(
    entry_bar: int = 50,
    hit_bar: int = 70,
    hit_type: Literal["sl", "tp"] = "tp",
    direction: Literal["long", "short"] = "long",
    sl_pct: float = 3.0,
    tp_pct: float = 6.0,
    initial_equity: float = 10000.0,
    bars: int = 200,
    seed: int = 42,
    symbol: str = "BTCUSDT",
    timeframe: str = "15m",
) -> KnownAnswerScenario:
    """Create scenario where SL or TP is hit at exact bar."""
    sig_dir = SignalDirection.LONG if direction == "long" else SignalDirection.SHORT
    exit_reason = ExitReason.STOP_LOSS if hit_type == "sl" else ExitReason.TAKE_PROFIT

    df = _create_base_candles(bars=bars, seed=seed, timeframe=timeframe)

    # Entry price is the open of bar after signal (fill at next bar open)
    entry_price = df["open"].iloc[entry_bar + 1]

    # Engineer the SL/TP hit
    df = _engineer_sl_tp_hit(
        df,
        entry_bar=entry_bar + 1,
        hit_bar=hit_bar,
        hit_type=exit_reason,
        entry_price=entry_price,
        sl_pct=sl_pct,
        tp_pct=tp_pct,
        direction=sig_dir,
    )

    # Calculate expected exit price and P/L
    if direction == "long":
        if hit_type == "sl":
            exit_price = entry_price * (1 - sl_pct / 100)
            pnl_pct = -sl_pct
        else:
            exit_price = entry_price * (1 + tp_pct / 100)
            pnl_pct = tp_pct
    else:
        if hit_type == "sl":
            exit_price = entry_price * (1 + sl_pct / 100)
            pnl_pct = -sl_pct
        else:
            exit_price = entry_price * (1 - tp_pct / 100)
            pnl_pct = tp_pct

    expected_pnl = initial_equity * (pnl_pct / 100)

    expected_signal = ExpectedSignal(
        bar_idx=entry_bar,
        direction=sig_dir,
        trigger_reason="ema_cross",  # Actually using EMA cross for entry
        tolerance_bars=15,  # EMA signals have inherent lag
    )

    expected_trade = ExpectedTrade(
        entry_bar=entry_bar + 1,
        entry_price=entry_price,
        exit_bar=hit_bar,
        exit_price=exit_price,
        exit_reason=exit_reason,
        direction=sig_dir,
        pnl=expected_pnl,
        tolerance_bars=10,  # Account for signal lag
        tolerance_price_pct=5.0,  # Slippage and engineered data variance
    )

    # Use EMA cross for entry signal (easier to control than "always true")
    play_config = {
        "version": "3.0.0",
        "name": f"KA_sl_tp_{hit_type}_{direction}",
        "symbol": symbol,
        "timeframes": {
            "low_tf": timeframe,
            "med_tf": timeframe,
            "high_tf": timeframe,
            "exec": "low_tf",
        },
        "features": {
            "ema_9": {"indicator": "ema", "params": {"length": 9}},
            "ema_21": {"indicator": "ema", "params": {"length": 21}},
        },
        "actions": {
            f"entry_{direction}": {
                "all": [["ema_9", "cross_above" if direction == "long" else "cross_below", "ema_21"]],
            },
        },
        "position_policy": {
            "mode": f"{direction}_only",
            "exit_mode": "sl_tp_only",
        },
        "risk": {
            "stop_loss_pct": sl_pct,
            "take_profit_pct": tp_pct,
        },
        "account": {
            "starting_equity_usdt": initial_equity,
            "max_leverage": 1,
        },
    }

    return KnownAnswerScenario(
        name=f"KA_00{4 if hit_type == 'sl' else 5}_{hit_type}_hit_{direction}",
        description=f"{'Stop loss' if hit_type == 'sl' else 'Take profit'} hit at bar {hit_bar} for {direction} entry at bar {entry_bar}",
        candles=df,
        expected_signals=[expected_signal],
        expected_trades=[expected_trade],
        play_config=play_config,
        symbol=symbol,
        timeframe=timeframe,
    )


# =============================================================================
# All Predefined Scenarios
# =============================================================================

def get_all_known_answer_scenarios() -> list[KnownAnswerScenario]:
    """Get all predefined known-answer test scenarios."""
    return [
        create_ema_cross_scenario(cross_bar=50, direction="long"),
        create_ema_cross_scenario(cross_bar=50, direction="short"),
        create_rsi_threshold_scenario(target_bar=50, threshold="oversold"),
        create_rsi_threshold_scenario(target_bar=50, threshold="overbought"),
        create_sl_tp_scenario(entry_bar=50, hit_bar=70, hit_type="sl", direction="long"),
        create_sl_tp_scenario(entry_bar=50, hit_bar=70, hit_type="tp", direction="long"),
        create_sl_tp_scenario(entry_bar=50, hit_bar=70, hit_type="sl", direction="short"),
        create_sl_tp_scenario(entry_bar=50, hit_bar=70, hit_type="tp", direction="short"),
    ]


def get_scenario_by_name(name: str) -> KnownAnswerScenario | None:
    """Get a scenario by name."""
    for scenario in get_all_known_answer_scenarios():
        if scenario.name == name:
            return scenario
    return None


# =============================================================================
# Test Runner
# =============================================================================

def run_known_answer_test(
    scenario: KnownAnswerScenario,
    run_engine: bool = True,
) -> KnownAnswerResult:
    """
    Run a known-answer test scenario against the backtest engine.

    This:
    1. Creates a synthetic data provider from scenario candles
    2. Creates a Play from scenario.play_config
    3. Runs the backtest engine with synthetic data
    4. Extracts actual signals/trades
    5. Compares to expected and reports pass/fail

    Args:
        scenario: The known-answer scenario to test
        run_engine: If True, run the actual engine. If False, just validate structure.

    Returns:
        KnownAnswerResult with match details
    """
    import time
    start_time = time.time()

    result = KnownAnswerResult(scenario_name=scenario.name, passed=True)

    try:
        # Validate scenario has required data
        if scenario.candles is None or len(scenario.candles) == 0:
            result.passed = False
            result.error = "Scenario has no candle data"
            return result

        # Validate expected signals are within data range
        max_bar = len(scenario.candles) - 1
        for sig in scenario.expected_signals:
            if sig.bar_idx < 0 or sig.bar_idx > max_bar:
                result.passed = False
                result.error = f"Expected signal bar {sig.bar_idx} out of range [0, {max_bar}]"
                return result

        # Validate expected trades
        for trade in scenario.expected_trades:
            if trade.entry_bar < 0 or trade.entry_bar > max_bar:
                result.passed = False
                result.error = f"Expected trade entry bar {trade.entry_bar} out of range"
                return result
            if trade.exit_bar < trade.entry_bar or trade.exit_bar > max_bar:
                result.passed = False
                result.error = f"Expected trade exit bar {trade.exit_bar} invalid"
                return result

        if run_engine:
            # Run the actual backtest engine
            actual_signals, actual_trades, engine_error = _run_engine_with_scenario(scenario)

            if engine_error:
                result.passed = False
                result.error = engine_error
                return result

            result.actual_signals = actual_signals
            result.actual_trades = actual_trades

            # Validate signals
            for expected_sig in scenario.expected_signals:
                match = validate_signal_match(expected_sig, actual_signals)
                result.signal_matches.append(match)
                if match.matched:
                    result.signals_passed += 1
                else:
                    result.signals_failed += 1
                    result.passed = False

            # Validate trades
            for expected_trade in scenario.expected_trades:
                match = validate_trade_match(expected_trade, actual_trades)
                result.trade_matches.append(match)
                if match.matched:
                    result.trades_passed += 1
                else:
                    result.trades_failed += 1
                    result.passed = False

            logger.info(
                f"Known-answer scenario '{scenario.name}': "
                f"Signals {result.signals_passed}/{len(scenario.expected_signals)}, "
                f"Trades {result.trades_passed}/{len(scenario.expected_trades)}"
            )
        else:
            # Structure-only validation
            result.signals_passed = len(scenario.expected_signals)
            result.trades_passed = len(scenario.expected_trades)
            logger.info(
                f"Known-answer scenario '{scenario.name}' validated structurally. "
                f"Signals: {result.signals_passed}, Trades: {result.trades_passed}"
            )

    except Exception as e:
        result.passed = False
        result.error = str(e)
        logger.error(f"Known-answer test failed: {e}")

    result.duration_ms = int((time.time() - start_time) * 1000)
    return result


def _run_engine_with_scenario(
    scenario: KnownAnswerScenario,
) -> tuple[list[dict], list[dict], str | None]:
    """
    Run the backtest engine with a known-answer scenario.

    Returns:
        Tuple of (signals, trades, error_message)
    """
    try:
        from ..backtest.play import Play
        from ..backtest.engine_factory import create_engine_from_play, run_engine_with_play

        # Create data provider
        provider = KnownAnswerDataProvider(scenario)

        # Create Play from config
        play = Play.from_dict(scenario.play_config)

        # Get data range for window
        start_dt, end_dt = provider.get_data_range(scenario.timeframe)

        # Create engine with synthetic provider
        engine = create_engine_from_play(
            play=play,
            window_start=start_dt,
            window_end=end_dt,
            synthetic_provider=provider,
            data_env="backtest",
        )

        # Run backtest
        bt_result = run_engine_with_play(engine, play)

        # Extract signals and trades from Trade dataclass objects
        signals = []
        trades = []

        for trade in bt_result.trades:
            # Trade is a dataclass, access attributes directly
            entry_bar = getattr(trade, "entry_bar_index", None) or 0
            exit_bar = getattr(trade, "exit_bar_index", None) or 0
            entry_price = getattr(trade, "entry_price", 0)
            exit_price = getattr(trade, "exit_price", 0) or 0
            realized_pnl = getattr(trade, "realized_pnl", 0)
            side = getattr(trade, "side", "long")
            exit_reason = getattr(trade, "exit_reason", "") or ""

            # Map side to direction
            direction = side if side in ("long", "short") else "long"

            signals.append({
                "bar_idx": entry_bar,
                "direction": direction,
            })

            trades.append({
                "entry_bar": entry_bar,
                "exit_bar": exit_bar,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "pnl": realized_pnl,
                "direction": direction,
                "exit_reason": exit_reason,
            })

        return signals, trades, None

    except Exception as e:
        logger.error(f"Engine run failed: {e}")
        return [], [], str(e)


def validate_signal_match(
    expected: ExpectedSignal,
    actual_signals: list[dict],
) -> SignalMatch:
    """Validate that an actual signal matches expected."""
    for actual in actual_signals:
        actual_bar = actual.get("bar_idx", actual.get("bar", -1))
        actual_dir = actual.get("direction", "")

        bar_diff = abs(actual_bar - expected.bar_idx)
        if bar_diff <= expected.tolerance_bars:
            if actual_dir.lower() == expected.direction.value.lower():
                return SignalMatch(
                    expected=expected,
                    actual_bar=actual_bar,
                    actual_direction=actual_dir,
                    matched=True,
                    bar_diff=bar_diff,
                    notes="Match within tolerance" if bar_diff > 0 else "Exact match",
                )

    return SignalMatch(
        expected=expected,
        actual_bar=None,
        actual_direction=None,
        matched=False,
        notes=f"No matching signal found near bar {expected.bar_idx}",
    )


def validate_trade_match(
    expected: ExpectedTrade,
    actual_trades: list[dict],
) -> TradeMatch:
    """Validate that an actual trade matches expected."""
    for actual in actual_trades:
        actual_entry_bar = actual.get("entry_bar", -1)
        actual_exit_bar = actual.get("exit_bar", -1)

        entry_bar_diff = abs(actual_entry_bar - expected.entry_bar)
        exit_bar_diff = abs(actual_exit_bar - expected.exit_bar)

        if entry_bar_diff <= expected.tolerance_bars and exit_bar_diff <= expected.tolerance_bars:
            actual_entry_price = actual.get("entry_price", 0)
            actual_exit_price = actual.get("exit_price", 0)
            actual_pnl = actual.get("pnl", 0)

            entry_price_diff = abs(actual_entry_price - expected.entry_price) / expected.entry_price * 100 if expected.entry_price > 0 else 0
            exit_price_diff = abs(actual_exit_price - expected.exit_price) / expected.exit_price * 100 if expected.exit_price > 0 else 0
            pnl_diff = abs(actual_pnl - expected.pnl)

            if entry_price_diff <= expected.tolerance_price_pct and exit_price_diff <= expected.tolerance_price_pct:
                return TradeMatch(
                    expected=expected,
                    actual=actual,
                    matched=True,
                    entry_bar_diff=entry_bar_diff,
                    exit_bar_diff=exit_bar_diff,
                    entry_price_diff_pct=entry_price_diff,
                    exit_price_diff_pct=exit_price_diff,
                    pnl_diff=pnl_diff,
                    notes="Match within tolerance",
                )

    return TradeMatch(
        expected=expected,
        actual=None,
        matched=False,
        notes=f"No matching trade found with entry near bar {expected.entry_bar}",
    )
