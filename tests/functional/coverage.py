"""
Coverage Matrix for Functional Tests.

Categorizes all indicators, structures, and operators by their PRIMARY usage:
- TRIGGER: Can generate entry/exit signals on its own
- CONTEXT: Provides filtering, sizing, or level information
- HYBRID: Can be used as either trigger or context

Test approach varies by category:
- TRIGGER: Test the indicator's signal generation directly
- CONTEXT: Combine with a simple trigger (EMA cross) and use as filter/sizing
- HYBRID: Test both modes
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class IndicatorRole(Enum):
    """Primary role of an indicator."""
    TRIGGER = "trigger"      # Generates signals (crossover, threshold)
    CONTEXT = "context"      # Provides filter/sizing info
    HYBRID = "hybrid"        # Can be either


class TriggerType(Enum):
    """How a trigger indicator generates signals."""
    THRESHOLD = "threshold"           # Crosses a level (RSI 30/70)
    CROSSOVER = "crossover"           # Line crosses line (MACD/signal)
    STATE_CHANGE = "state_change"     # Direction flips (SuperTrend)
    BAND_TOUCH = "band_touch"         # Price touches band (BB upper/lower)
    ZERO_CROSS = "zero_cross"         # Crosses zero line


class ContextType(Enum):
    """How a context indicator provides information."""
    VOLATILITY = "volatility"         # ATR, NATR - for sizing/stops
    TREND_STRENGTH = "trend_strength" # ADX - filter weak trends
    LEVEL = "level"                   # MA, VWAP - support/resistance
    VOLUME = "volume"                 # OBV, CMF - confirmation
    MOMENTUM = "momentum"             # ROC, MOM - confirmation


@dataclass
class IndicatorCoverage:
    """Coverage metadata for a single indicator."""
    name: str
    role: IndicatorRole
    trigger_type: TriggerType | None = None
    context_type: ContextType | None = None
    test_condition: str = ""          # DSL condition to test
    typical_params: dict[str, Any] | None = None
    notes: str = ""


# =============================================================================
# INDICATOR COVERAGE MATRIX (43 indicators)
# =============================================================================

INDICATOR_COVERAGE: dict[str, IndicatorCoverage] = {
    # -------------------------------------------------------------------------
    # THRESHOLD TRIGGERS - Cross a numeric level
    # -------------------------------------------------------------------------
    "rsi": IndicatorCoverage(
        name="rsi",
        role=IndicatorRole.TRIGGER,
        trigger_type=TriggerType.THRESHOLD,
        test_condition='["rsi_14", "cross_below", 30]',  # Oversold
        typical_params={"length": 14},
        notes="Classic momentum oscillator. Test oversold bounce.",
    ),
    "cci": IndicatorCoverage(
        name="cci",
        role=IndicatorRole.TRIGGER,
        trigger_type=TriggerType.THRESHOLD,
        test_condition='["cci_20", "cross_above", -100]',  # Oversold recovery
        typical_params={"length": 20},
        notes="Commodity Channel Index. +100/-100 thresholds.",
    ),
    "willr": IndicatorCoverage(
        name="willr",
        role=IndicatorRole.TRIGGER,
        trigger_type=TriggerType.THRESHOLD,
        test_condition='["willr_14", "cross_above", -80]',  # Oversold recovery
        typical_params={"length": 14},
        notes="Williams %R. -20/-80 thresholds (inverted scale).",
    ),
    "mfi": IndicatorCoverage(
        name="mfi",
        role=IndicatorRole.TRIGGER,
        trigger_type=TriggerType.THRESHOLD,
        test_condition='["mfi_14", "cross_above", 20]',  # Oversold recovery
        typical_params={"length": 14},
        notes="Money Flow Index. Volume-weighted RSI. 20/80 thresholds.",
    ),
    "cmo": IndicatorCoverage(
        name="cmo",
        role=IndicatorRole.TRIGGER,
        trigger_type=TriggerType.ZERO_CROSS,
        test_condition='["cmo_14", "cross_above", 0]',  # Bullish
        typical_params={"length": 14},
        notes="Chande Momentum Oscillator. Zero-line cross.",
    ),
    "trix": IndicatorCoverage(
        name="trix",
        role=IndicatorRole.TRIGGER,
        trigger_type=TriggerType.ZERO_CROSS,
        test_condition='[{"feature_id": "trix_18", "field": "trix"}, "cross_above", 0]',  # Bullish
        typical_params={"length": 18},
        notes="Triple EMA rate of change. Zero-line cross.",
    ),
    "uo": IndicatorCoverage(
        name="uo",
        role=IndicatorRole.TRIGGER,
        trigger_type=TriggerType.THRESHOLD,
        test_condition='["uo_7_14_28", "cross_above", 30]',  # Oversold recovery
        typical_params={"fast": 7, "medium": 14, "slow": 28},
        notes="Ultimate Oscillator. 30/70 thresholds.",
    ),
    "ppo": IndicatorCoverage(
        name="ppo",
        role=IndicatorRole.TRIGGER,
        trigger_type=TriggerType.ZERO_CROSS,
        test_condition='[{"feature_id": "ppo_12_26_9", "field": "ppo"}, "cross_above", 0]',  # Bullish
        typical_params={"fast": 12, "slow": 26, "signal": 9},
        notes="Percentage Price Oscillator. Zero-line cross.",
    ),

    # -------------------------------------------------------------------------
    # CROSSOVER TRIGGERS - Line crosses another line
    # -------------------------------------------------------------------------
    "macd": IndicatorCoverage(
        name="macd",
        role=IndicatorRole.TRIGGER,
        trigger_type=TriggerType.CROSSOVER,
        test_condition='[{"feature_id": "macd_12_26_9", "field": "macd"}, "cross_above", {"feature_id": "macd_12_26_9", "field": "signal"}]',
        typical_params={"fast": 12, "slow": 26, "signal": 9},
        notes="MACD line crosses signal line. Classic momentum signal.",
    ),
    "stoch": IndicatorCoverage(
        name="stoch",
        role=IndicatorRole.TRIGGER,
        trigger_type=TriggerType.CROSSOVER,
        test_condition='[{"feature_id": "stoch_14_3_3", "field": "k"}, "cross_above", {"feature_id": "stoch_14_3_3", "field": "d"}]',
        typical_params={"k": 14, "d": 3, "smooth_k": 3},
        notes="Stochastic %K crosses %D. Also has 20/80 thresholds.",
    ),
    "stochrsi": IndicatorCoverage(
        name="stochrsi",
        role=IndicatorRole.TRIGGER,
        trigger_type=TriggerType.CROSSOVER,
        test_condition='[{"feature_id": "stochrsi_14_14_3_3", "field": "k"}, "cross_above", {"feature_id": "stochrsi_14_14_3_3", "field": "d"}]',
        typical_params={"length": 14, "rsi_length": 14, "k": 3, "d": 3},
        notes="Stochastic RSI. More sensitive than regular stochastic.",
    ),
    "aroon": IndicatorCoverage(
        name="aroon",
        role=IndicatorRole.TRIGGER,
        trigger_type=TriggerType.CROSSOVER,
        test_condition='[{"feature_id": "aroon_25", "field": "up"}, "cross_above", {"feature_id": "aroon_25", "field": "down"}]',
        typical_params={"length": 25},
        notes="Aroon Up crosses Aroon Down. Trend identification.",
    ),
    "vortex": IndicatorCoverage(
        name="vortex",
        role=IndicatorRole.TRIGGER,
        trigger_type=TriggerType.CROSSOVER,
        test_condition='[{"feature_id": "vortex_14", "field": "vip"}, "cross_above", {"feature_id": "vortex_14", "field": "vim"}]',
        typical_params={"length": 14},
        notes="VI+ crosses VI-. Trend direction signal.",
    ),
    "fisher": IndicatorCoverage(
        name="fisher",
        role=IndicatorRole.TRIGGER,
        trigger_type=TriggerType.CROSSOVER,
        test_condition='[{"feature_id": "fisher_9", "field": "fisher"}, "cross_above", {"feature_id": "fisher_9", "field": "signal"}]',
        typical_params={"length": 9},
        notes="Fisher Transform crosses signal. Sharp turning point indicator.",
    ),
    "tsi": IndicatorCoverage(
        name="tsi",
        role=IndicatorRole.TRIGGER,
        trigger_type=TriggerType.CROSSOVER,
        test_condition='[{"feature_id": "tsi_13_25_13", "field": "tsi"}, "cross_above", {"feature_id": "tsi_13_25_13", "field": "signal"}]',
        typical_params={"fast": 13, "slow": 25, "signal": 13},
        notes="True Strength Index crosses signal. Double-smoothed momentum.",
    ),
    "kvo": IndicatorCoverage(
        name="kvo",
        role=IndicatorRole.TRIGGER,
        trigger_type=TriggerType.CROSSOVER,
        test_condition='[{"feature_id": "kvo_34_55_13", "field": "kvo"}, "cross_above", {"feature_id": "kvo_34_55_13", "field": "signal"}]',
        typical_params={"fast": 34, "slow": 55, "signal": 13},
        notes="Klinger Volume Oscillator crosses signal. Volume-based.",
    ),

    # -------------------------------------------------------------------------
    # STATE CHANGE TRIGGERS - Direction or state flips
    # -------------------------------------------------------------------------
    "supertrend": IndicatorCoverage(
        name="supertrend",
        role=IndicatorRole.TRIGGER,
        trigger_type=TriggerType.STATE_CHANGE,
        test_condition='[{"feature_id": "supertrend_10_3", "field": "direction"}, "cross_above", 0]',
        typical_params={"length": 10, "multiplier": 3.0},
        notes="Direction crosses above 0 (from -1 to 1). Trend-following signal.",
    ),
    "psar": IndicatorCoverage(
        name="psar",
        role=IndicatorRole.TRIGGER,
        trigger_type=TriggerType.STATE_CHANGE,
        test_condition='[{"feature_id": "psar_0.02_0.02_0.2", "field": "reversal"}, "gt", 0]',
        typical_params={"af0": 0.02, "af": 0.02, "max_af": 0.2},
        notes="Parabolic SAR reversal signal. reversal > 0 means direction change.",
    ),
    "squeeze": IndicatorCoverage(
        name="squeeze",
        role=IndicatorRole.HYBRID,
        trigger_type=TriggerType.STATE_CHANGE,
        context_type=ContextType.VOLATILITY,
        test_condition='[{"feature_id": "squeeze_20_2_20_1.5", "field": "off"}, "gt", 0]',
        typical_params={"bb_length": 20, "bb_std": 2.0, "kc_length": 20, "kc_scalar": 1.5},
        notes="Squeeze fires when volatility expands (off > 0). Context: squeeze on = low vol.",
    ),

    # -------------------------------------------------------------------------
    # LEVEL/BAND INDICATORS - Price relative to level
    # -------------------------------------------------------------------------
    "ema": IndicatorCoverage(
        name="ema",
        role=IndicatorRole.HYBRID,
        trigger_type=TriggerType.CROSSOVER,
        context_type=ContextType.LEVEL,
        test_condition='["ema_9", "cross_above", "ema_21"]',
        typical_params={"length": 20},
        notes="Trigger: EMA crossover. Context: price vs EMA as trend filter.",
    ),
    "sma": IndicatorCoverage(
        name="sma",
        role=IndicatorRole.HYBRID,
        trigger_type=TriggerType.CROSSOVER,
        context_type=ContextType.LEVEL,
        test_condition='["sma_10", "cross_above", "sma_30"]',
        typical_params={"length": 20},
        notes="Trigger: SMA crossover. Context: price vs SMA as trend filter.",
    ),
    "wma": IndicatorCoverage(
        name="wma",
        role=IndicatorRole.CONTEXT,
        context_type=ContextType.LEVEL,
        test_condition='["close", ">", "wma_20"]',
        typical_params={"length": 20},
        notes="Weighted MA. Similar to EMA but different weighting.",
    ),
    "dema": IndicatorCoverage(
        name="dema",
        role=IndicatorRole.CONTEXT,
        context_type=ContextType.LEVEL,
        test_condition='["close", ">", "dema_20"]',
        typical_params={"length": 20},
        notes="Double EMA. Less lag than EMA.",
    ),
    "tema": IndicatorCoverage(
        name="tema",
        role=IndicatorRole.CONTEXT,
        context_type=ContextType.LEVEL,
        test_condition='["close", ">", "tema_20"]',
        typical_params={"length": 20},
        notes="Triple EMA. Even less lag.",
    ),
    "trima": IndicatorCoverage(
        name="trima",
        role=IndicatorRole.CONTEXT,
        context_type=ContextType.LEVEL,
        test_condition='["close", ">", "trima_20"]',
        typical_params={"length": 20},
        notes="Triangular MA. Smoother than SMA.",
    ),
    "zlma": IndicatorCoverage(
        name="zlma",
        role=IndicatorRole.CONTEXT,
        context_type=ContextType.LEVEL,
        test_condition='["close", ">", "zlma_20"]',
        typical_params={"length": 20},
        notes="Zero-Lag MA. Attempts to remove lag.",
    ),
    "kama": IndicatorCoverage(
        name="kama",
        role=IndicatorRole.CONTEXT,
        context_type=ContextType.LEVEL,
        test_condition='["close", ">", "kama_20"]',
        typical_params={"length": 20},
        notes="Kaufman Adaptive MA. Adjusts to volatility.",
    ),
    "alma": IndicatorCoverage(
        name="alma",
        role=IndicatorRole.CONTEXT,
        context_type=ContextType.LEVEL,
        test_condition='["close", ">", "alma_20"]',
        typical_params={"length": 20, "sigma": 6, "offset": 0.85},
        notes="Arnaud Legoux MA. Gaussian-weighted.",
    ),
    "bbands": IndicatorCoverage(
        name="bbands",
        role=IndicatorRole.HYBRID,
        trigger_type=TriggerType.BAND_TOUCH,
        context_type=ContextType.LEVEL,
        test_condition='["close", "<", {"feature_id": "bbands_20_2", "field": "lower"}]',
        typical_params={"length": 20, "std": 2.0},
        notes="Trigger: price at bands. Context: %B, bandwidth for volatility.",
    ),
    "kc": IndicatorCoverage(
        name="kc",
        role=IndicatorRole.HYBRID,
        trigger_type=TriggerType.BAND_TOUCH,
        context_type=ContextType.LEVEL,
        test_condition='["close", ">", {"feature_id": "kc_20_1.5", "field": "upper"}]',
        typical_params={"length": 20, "scalar": 1.5},
        notes="Keltner Channel. ATR-based bands.",
    ),
    "donchian": IndicatorCoverage(
        name="donchian",
        role=IndicatorRole.TRIGGER,
        trigger_type=TriggerType.BAND_TOUCH,
        test_condition='["close", "cross_above", {"feature_id": "donchian_20_20", "field": "middle"}]',
        typical_params={"lower_length": 20, "upper_length": 20},
        notes="Donchian Channel. Cross above middle for trend-following.",
    ),
    "vwap": IndicatorCoverage(
        name="vwap",
        role=IndicatorRole.CONTEXT,
        context_type=ContextType.LEVEL,
        test_condition='["close", ">", "vwap_D"]',
        typical_params={"anchor": "D"},
        notes="Volume-Weighted Average Price. Intraday level.",
    ),
    "linreg": IndicatorCoverage(
        name="linreg",
        role=IndicatorRole.CONTEXT,
        context_type=ContextType.LEVEL,
        test_condition='["close", ">", "linreg_20"]',
        typical_params={"length": 20},
        notes="Linear regression line. Trend direction.",
    ),
    "midprice": IndicatorCoverage(
        name="midprice",
        role=IndicatorRole.CONTEXT,
        context_type=ContextType.LEVEL,
        test_condition='["close", ">", "midprice_14"]',
        typical_params={"length": 14},
        notes="Midpoint of high/low range.",
    ),

    # -------------------------------------------------------------------------
    # CONTEXT INDICATORS - Volatility, Trend Strength, Volume
    # -------------------------------------------------------------------------
    "atr": IndicatorCoverage(
        name="atr",
        role=IndicatorRole.CONTEXT,
        context_type=ContextType.VOLATILITY,
        test_condition='["atr_14", ">", 0]',  # Just verify it computes
        typical_params={"length": 14},
        notes="Average True Range. Used for stops and sizing. NOT a trigger.",
    ),
    "natr": IndicatorCoverage(
        name="natr",
        role=IndicatorRole.CONTEXT,
        context_type=ContextType.VOLATILITY,
        test_condition='["natr_14", ">", 0]',  # Just verify it computes
        typical_params={"length": 14},
        notes="Normalized ATR (%). Compare volatility across assets.",
    ),
    "adx": IndicatorCoverage(
        name="adx",
        role=IndicatorRole.CONTEXT,
        context_type=ContextType.TREND_STRENGTH,
        test_condition='[{"feature_id": "adx_14", "field": "adx"}, ">", 25]',
        typical_params={"length": 14},
        notes="ADX > 25 = trending. Used as filter, NOT trigger.",
    ),
    "dm": IndicatorCoverage(
        name="dm",
        role=IndicatorRole.CONTEXT,
        context_type=ContextType.TREND_STRENGTH,
        test_condition='[{"feature_id": "dm_14", "field": "dmp"}, ">", {"feature_id": "dm_14", "field": "dmn"}]',
        typical_params={"length": 14},
        notes="Directional Movement. DM+ > DM- = bullish bias.",
    ),
    "obv": IndicatorCoverage(
        name="obv",
        role=IndicatorRole.CONTEXT,
        context_type=ContextType.VOLUME,
        test_condition='["obv", ">", 0]',  # Just verify it computes
        typical_params={},
        notes="On-Balance Volume. Cumulative. Confirms price moves.",
    ),
    "cmf": IndicatorCoverage(
        name="cmf",
        role=IndicatorRole.CONTEXT,
        context_type=ContextType.VOLUME,
        test_condition='["cmf_20", ">", 0]',  # Positive = buying pressure
        typical_params={"length": 20},
        notes="Chaikin Money Flow. > 0 = buying, < 0 = selling.",
    ),

    # -------------------------------------------------------------------------
    # MOMENTUM INDICATORS - Rate of change
    # -------------------------------------------------------------------------
    "mom": IndicatorCoverage(
        name="mom",
        role=IndicatorRole.HYBRID,
        trigger_type=TriggerType.ZERO_CROSS,
        context_type=ContextType.MOMENTUM,
        test_condition='["mom_10", "cross_above", 0]',
        typical_params={"length": 10},
        notes="Momentum. Price change over N periods.",
    ),
    "roc": IndicatorCoverage(
        name="roc",
        role=IndicatorRole.HYBRID,
        trigger_type=TriggerType.ZERO_CROSS,
        context_type=ContextType.MOMENTUM,
        test_condition='["roc_10", "cross_above", 0]',
        typical_params={"length": 10},
        notes="Rate of Change (%). Similar to momentum.",
    ),

    # -------------------------------------------------------------------------
    # UTILITY INDICATORS - Price transforms
    # -------------------------------------------------------------------------
    "ohlc4": IndicatorCoverage(
        name="ohlc4",
        role=IndicatorRole.CONTEXT,
        context_type=ContextType.LEVEL,
        test_condition='["ohlc4", ">", 0]',  # Just verify it computes
        typical_params={},
        notes="Average of OHLC. Smoothed price. Used as input to other indicators.",
    ),
}


# =============================================================================
# STRUCTURE COVERAGE (6 structures)
# =============================================================================

@dataclass
class StructureCoverage:
    """Coverage metadata for a structure type."""
    name: str
    description: str
    test_outputs: list[str]  # Key outputs to test
    depends_on: str | None = None
    notes: str = ""


STRUCTURE_COVERAGE: dict[str, StructureCoverage] = {
    "swing": StructureCoverage(
        name="swing",
        description="Swing high/low detection",
        test_outputs=["high_level", "low_level", "high_idx", "low_idx"],
        notes="Foundation for many other structures. Test pivot detection.",
    ),
    "fibonacci": StructureCoverage(
        name="fibonacci",
        description="Fibonacci retracement/extension levels",
        test_outputs=["level_0.382", "level_0.5", "level_0.618"],
        depends_on="swing",
        notes="Derived from swing pivots. Test level computation.",
    ),
    "zone": StructureCoverage(
        name="zone",
        description="Supply/demand zones",
        test_outputs=["state", "upper", "lower"],
        depends_on="swing",
        notes="Zone states: NONE, ACTIVE, BROKEN. Test state transitions.",
    ),
    "trend": StructureCoverage(
        name="trend",
        description="Trend classification",
        test_outputs=["direction", "strength", "bars_in_trend"],
        depends_on="swing",
        notes="Direction: UP, DOWN, SIDEWAYS. Test trend detection.",
    ),
    "rolling_window": StructureCoverage(
        name="rolling_window",
        description="O(1) rolling min/max",
        test_outputs=["value"],
        notes="Efficient rolling calculations. Test min/max accuracy.",
    ),
    "derived_zone": StructureCoverage(
        name="derived_zone",
        description="Fibonacci zones from pivots with K slots",
        test_outputs=["zone0_state", "any_active", "closest_active_lower"],
        depends_on="swing",
        notes="K slots + aggregates pattern. Test slot management.",
    ),
}


# =============================================================================
# DSL OPERATOR COVERAGE (20 operators)
# =============================================================================

@dataclass
class OperatorCoverage:
    """Coverage metadata for a DSL operator."""
    name: str
    category: str  # comparison, boolean, window
    example: str
    valid_types: list[str]  # FLOAT, INT, BOOL, ENUM
    notes: str = ""


OPERATOR_COVERAGE: dict[str, OperatorCoverage] = {
    # Comparison operators
    "gt": OperatorCoverage("gt", "comparison", '["rsi_14", ">", 50]', ["FLOAT", "INT"], "Greater than. Alias: >"),
    "lt": OperatorCoverage("lt", "comparison", '["rsi_14", "<", 30]', ["FLOAT", "INT"], "Less than. Alias: <"),
    "gte": OperatorCoverage("gte", "comparison", '["rsi_14", ">=", 70]', ["FLOAT", "INT"], "Greater or equal. Alias: >=, ge"),
    "lte": OperatorCoverage("lte", "comparison", '["rsi_14", "<=", 30]', ["FLOAT", "INT"], "Less or equal. Alias: <=, le"),
    "eq": OperatorCoverage("eq", "comparison", '["direction", "==", 1]', ["INT", "BOOL", "ENUM"], "Equal. NO FLOATS. Alias: =="),
    "between": OperatorCoverage("between", "comparison", '["rsi_14", "between", [30, 70]]', ["FLOAT", "INT"], "Inclusive range check."),
    "near_abs": OperatorCoverage("near_abs", "comparison", '["close", "near_abs", "vwap", 10]', ["FLOAT"], "Within absolute tolerance."),
    "near_pct": OperatorCoverage("near_pct", "comparison", '["close", "near_pct", "ema_20", 0.01]', ["FLOAT"], "Within percentage tolerance."),
    "in": OperatorCoverage("in", "comparison", '["state", "in", ["ACTIVE", "TOUCHED"]]', ["INT", "ENUM"], "Membership test. NO FLOATS."),

    # Crossover operators
    "cross_above": OperatorCoverage("cross_above", "crossover", '["ema_9", "cross_above", "ema_21"]', ["FLOAT", "INT"], "prev <= rhs AND curr > rhs"),
    "cross_below": OperatorCoverage("cross_below", "crossover", '["rsi_14", "cross_below", 30]', ["FLOAT", "INT"], "prev >= rhs AND curr < rhs"),

    # Boolean operators
    "all": OperatorCoverage("all", "boolean", 'all: [cond1, cond2]', ["BOOL"], "AND - all conditions must be true"),
    "any": OperatorCoverage("any", "boolean", 'any: [cond1, cond2]', ["BOOL"], "OR - at least one must be true"),
    "not": OperatorCoverage("not", "boolean", 'not: {condition}', ["BOOL"], "Negation"),

    # Window operators
    "holds_for": OperatorCoverage("holds_for", "window", 'holds_for: {bars: 3, expr: [...]}', ["BOOL"], "True for N consecutive bars"),
    "occurred_within": OperatorCoverage("occurred_within", "window", 'occurred_within: {bars: 10, expr: [...]}', ["BOOL"], "True at least once in N bars"),
    "count_true": OperatorCoverage("count_true", "window", 'count_true: {bars: 10, min_count: 3, expr: [...]}', ["BOOL"], "True M+ times in N bars"),

    # Duration-based window operators
    "holds_for_duration": OperatorCoverage("holds_for_duration", "window", 'holds_for_duration: {duration: "30m", expr: [...]}', ["BOOL"], "True for time duration"),
    "occurred_within_duration": OperatorCoverage("occurred_within_duration", "window", 'occurred_within_duration: {duration: "1h", expr: [...]}', ["BOOL"], "True within time duration"),
    "count_true_duration": OperatorCoverage("count_true_duration", "window", 'count_true_duration: {duration: "4h", min_count: 5, expr: [...]}', ["BOOL"], "Count within time duration"),
}


# =============================================================================
# COVERAGE SUMMARY
# =============================================================================

def get_coverage_summary() -> dict[str, Any]:
    """Get summary of coverage status."""
    return {
        "indicators": {
            "total": len(INDICATOR_COVERAGE),
            "triggers": sum(1 for i in INDICATOR_COVERAGE.values() if i.role == IndicatorRole.TRIGGER),
            "context": sum(1 for i in INDICATOR_COVERAGE.values() if i.role == IndicatorRole.CONTEXT),
            "hybrid": sum(1 for i in INDICATOR_COVERAGE.values() if i.role == IndicatorRole.HYBRID),
        },
        "structures": {
            "total": len(STRUCTURE_COVERAGE),
        },
        "operators": {
            "total": len(OPERATOR_COVERAGE),
            "comparison": sum(1 for o in OPERATOR_COVERAGE.values() if o.category == "comparison"),
            "crossover": sum(1 for o in OPERATOR_COVERAGE.values() if o.category == "crossover"),
            "boolean": sum(1 for o in OPERATOR_COVERAGE.values() if o.category == "boolean"),
            "window": sum(1 for o in OPERATOR_COVERAGE.values() if o.category == "window"),
        },
    }


def print_coverage_summary():
    """Print coverage summary to console."""
    summary = get_coverage_summary()

    print("\n" + "=" * 60)
    print("  FUNCTIONAL TEST COVERAGE MATRIX")
    print("=" * 60)

    print(f"\n  INDICATORS: {summary['indicators']['total']} total")
    print(f"    - Triggers: {summary['indicators']['triggers']}")
    print(f"    - Context:  {summary['indicators']['context']}")
    print(f"    - Hybrid:   {summary['indicators']['hybrid']}")

    print(f"\n  STRUCTURES: {summary['structures']['total']} total")

    print(f"\n  OPERATORS: {summary['operators']['total']} total")
    print(f"    - Comparison: {summary['operators']['comparison']}")
    print(f"    - Crossover:  {summary['operators']['crossover']}")
    print(f"    - Boolean:    {summary['operators']['boolean']}")
    print(f"    - Window:     {summary['operators']['window']}")

    print("=" * 60 + "\n")


if __name__ == "__main__":
    print_coverage_summary()
