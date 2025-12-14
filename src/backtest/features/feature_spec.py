"""
FeatureSpec: Declarative indicator specification.

Provides a declarative way to specify indicators that strategies need.
Each FeatureSpec defines:
- indicator_type: What indicator to compute (EMA, RSI, ATR, MACD, etc.)
- input_source: What data to use as input (close, high, low, or another indicator)
- params: Parameters for the indicator (length, etc.)
- output_key: Name prefix for outputs (multi-output indicators append suffixes)
- outputs: For multi-output indicators, mapping of output names to keys

Design principles:
- Immutable specs (frozen dataclasses)
- Vectorized computation via FeatureFrameBuilder
- Compatible with FeedStore arrays (float32 preferred)
- Decoupled from strategy logic
- Proper warmup calculations per indicator type
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple


class IndicatorType(str, Enum):
    """
    Supported indicator types from pandas_ta library.
    
    Each type maps to a specific computation function in indicator_vendor.
    Reference: `reference/pandas_ta_repo/` for source code.
    
    **Total: 150+ indicators across 9 categories:**
    - Momentum (45): RSI, MACD, STOCH, CCI, ADX, etc.
    - Overlap (37): EMA, SMA, HMA, VWAP, Supertrend, etc.
    - Volatility (14): ATR, BBANDS, KC, Donchian, etc.
    - Volume (17): OBV, CMF, MFI, VWAP, etc.
    - Trend (19): ADX, PSAR, Aroon, etc.
    - Statistics (10): ZScore, Entropy, etc.
    - Performance (3): Drawdown, Returns
    - Cycles (2): EBSW, DSP
    - Candles (5): Heikin-Ashi, patterns
    
    Multi-output indicators return DataFrames with multiple columns.
    See MULTI_OUTPUT_KEYS for output column names.
    """
    # =========================================================================
    # MOMENTUM INDICATORS (45)
    # =========================================================================
    AO = "ao"              # Awesome Oscillator
    APO = "apo"            # Absolute Price Oscillator
    BIAS = "bias"          # Bias
    BOP = "bop"            # Balance of Power
    BRAR = "brar"          # BRAR (multi-output: ar, br)
    CCI = "cci"            # Commodity Channel Index
    CFO = "cfo"            # Chande Forecast Oscillator
    CG = "cg"              # Center of Gravity
    CMO = "cmo"            # Chande Momentum Oscillator
    COPPOCK = "coppock"    # Coppock Curve
    CTI = "cti"            # Correlation Trend Indicator
    DM = "dm"              # Directional Movement (multi-output: dmp, dmn)
    ER = "er"              # Efficiency Ratio
    ERI = "eri"            # Elder Ray Index (multi-output: bull, bear)
    FISHER = "fisher"      # Fisher Transform (multi-output: fisher, signal)
    INERTIA = "inertia"    # Inertia
    KDJ = "kdj"            # KDJ (multi-output: k, d, j)
    KST = "kst"            # Know Sure Thing (multi-output: kst, signal)
    LRSI = "lrsi"          # Laguerre RSI
    MACD = "macd"          # MACD (multi-output: macd, signal, histogram)
    MOM = "mom"            # Momentum
    PGO = "pgo"            # Pretty Good Oscillator
    PO = "po"              # Price Oscillator
    PPO = "ppo"            # Percentage Price Oscillator (multi-output: ppo, signal, histogram)
    PSL = "psl"            # Psychological Line
    PVO = "pvo"            # Percentage Volume Oscillator (multi-output: pvo, signal, histogram)
    QQE = "qqe"            # Quantitative Qualitative Estimation (multi-output)
    ROC = "roc"            # Rate of Change
    RSI = "rsi"            # Relative Strength Index
    RSX = "rsx"            # Relative Strength Index (Smoothed)
    RVGI = "rvgi"          # Relative Vigor Index (multi-output: rvgi, signal)
    SLOPE = "slope"        # Slope
    SMI = "smi"            # Stochastic Momentum Index (multi-output: smi, signal)
    SQUEEZE = "squeeze"    # Squeeze (multi-output: sqz, sqz_on, sqz_off, no_sqz)
    SQUEEZE_PRO = "squeeze_pro"  # Squeeze Pro (multi-output)
    STC = "stc"            # Schaff Trend Cycle (multi-output: stc, macd, stoch)
    STOCH = "stoch"        # Stochastic Oscillator (multi-output: k, d)
    STOCHRSI = "stochrsi"  # Stochastic RSI (multi-output: k, d)
    TD_SEQ = "td_seq"      # TD Sequential
    TRIX = "trix"          # TRIX (multi-output: trix, signal)
    TRIXH = "trixh"        # TRIX Histogram
    TSI = "tsi"            # True Strength Index (multi-output: tsi, signal)
    UO = "uo"              # Ultimate Oscillator
    VWMACD = "vwmacd"      # Volume Weighted MACD (multi-output)
    WILLR = "willr"        # Williams %R
    
    # =========================================================================
    # OVERLAP / MOVING AVERAGES (37)
    # =========================================================================
    ALMA = "alma"          # Arnaud Legoux Moving Average
    DEMA = "dema"          # Double Exponential Moving Average
    EMA = "ema"            # Exponential Moving Average
    FWMA = "fwma"          # Fibonacci Weighted Moving Average
    HILO = "hilo"          # High-Low Average (multi-output: hilo, hilos)
    HL2 = "hl2"            # High-Low Average (HL2)
    HLC3 = "hlc3"          # High-Low-Close Average (HLC3)
    HMA = "hma"            # Hull Moving Average
    HWMA = "hwma"          # Holt-Winter Moving Average
    ICHIMOKU = "ichimoku"  # Ichimoku Cloud (multi-output: many)
    JMA = "jma"            # Jurik Moving Average
    KAMA = "kama"          # Kaufman Adaptive Moving Average
    LINREG = "linreg"      # Linear Regression (multi-output: lr, slope, intercept, r, stderr)
    MA = "ma"              # Generic Moving Average
    MCGD = "mcgd"          # McGinley Dynamic
    MIDPOINT = "midpoint"  # Midpoint
    MIDPRICE = "midprice"  # Midprice
    MMAR = "mmar"          # Moving Average Ribbon (multi-output)
    OHLC4 = "ohlc4"        # OHLC4 Average
    PWMA = "pwma"          # Pascals Weighted Moving Average
    RAINBOW = "rainbow"    # Rainbow Moving Average (multi-output)
    RMA = "rma"            # Rolling Moving Average (Wilder's Smoothing)
    SINWMA = "sinwma"      # Sine Weighted Moving Average
    SMA = "sma"            # Simple Moving Average
    SSF = "ssf"            # Ehlers Super Smoother Filter
    SUPERTREND = "supertrend"  # Supertrend (multi-output: trend, direction, long, short)
    SWMA = "swma"          # Symmetric Weighted Moving Average
    T3 = "t3"              # T3 Moving Average
    TEMA = "tema"          # Triple Exponential Moving Average
    TRIMA = "trima"        # Triangular Moving Average
    VIDYA = "vidya"        # Variable Index Dynamic Average
    VWAP = "vwap"          # Volume Weighted Average Price
    VWMA = "vwma"          # Volume Weighted Moving Average
    WCP = "wcp"            # Weighted Close Price
    WMA = "wma"            # Weighted Moving Average
    ZLMA = "zlma"          # Zero Lag Moving Average
    
    # =========================================================================
    # VOLATILITY INDICATORS (14)
    # =========================================================================
    ABERRATION = "aberration"  # Aberration (multi-output: atr, zg, sg, xg)
    ACCBANDS = "accbands"      # Acceleration Bands (multi-output: lower, mid, upper)
    ATR = "atr"                # Average True Range
    BBANDS = "bbands"          # Bollinger Bands (multi-output: lower, mid, upper, bandwidth, percent_b)
    DONCHIAN = "donchian"      # Donchian Channel (multi-output: lower, mid, upper)
    HWC = "hwc"                # Holt-Winter Channel (multi-output)
    KC = "kc"                  # Keltner Channel (multi-output: lower, basis, upper)
    MASSI = "massi"            # Mass Index
    NATR = "natr"              # Normalized Average True Range
    PDIST = "pdist"            # Price Distance
    RVI = "rvi"                # Relative Volatility Index
    THERMO = "thermo"          # Elder's Thermometer (multi-output: thermo, ma, long, short)
    TRUE_RANGE = "true_range"  # True Range
    UI = "ui"                  # Ulcer Index
    
    # =========================================================================
    # VOLUME INDICATORS (17)
    # =========================================================================
    AD = "ad"              # Accumulation/Distribution
    ADOSC = "adosc"        # Accumulation/Distribution Oscillator
    AOBV = "aobv"          # Awesome OBV (multi-output)
    CMF = "cmf"            # Chaikin Money Flow
    EFI = "efi"            # Elder Force Index
    EOM = "eom"            # Ease of Movement
    KVO = "kvo"            # Klinger Volume Oscillator (multi-output: kvo, signal)
    MFI = "mfi"            # Money Flow Index
    NVI = "nvi"            # Negative Volume Index
    OBV = "obv"            # On Balance Volume
    PVI = "pvi"            # Positive Volume Index
    PVOL = "pvol"          # Price Volume
    PVR = "pvr"            # Price Volume Rank
    PVT = "pvt"            # Price Volume Trend
    VFI = "vfi"            # Volume Flow Indicator
    VP = "vp"              # Volume Profile (multi-output)
    
    # =========================================================================
    # TREND INDICATORS (19)
    # =========================================================================
    ADX = "adx"            # Average Directional Index (multi-output: adx, dmp, dmn)
    AMAT = "amat"          # Archer Moving Averages Trends (multi-output)
    AROON = "aroon"        # Aroon (multi-output: up, down, osc)
    CHOP = "chop"          # Choppiness Index
    CKSP = "cksp"          # Chande Kroll Stop (multi-output: long, short)
    DECAY = "decay"        # Decay
    DECREASING = "decreasing"  # Decreasing (utility)
    DPO = "dpo"            # Detrended Price Oscillator
    INCREASING = "increasing"  # Increasing (utility)
    LONG_RUN = "long_run"  # Long Run (utility)
    PMAX = "pmax"          # Profit Maximizer (multi-output)
    PSAR = "psar"          # Parabolic SAR (multi-output: long, short, af, reversal)
    QSTICK = "qstick"      # QStick
    SHORT_RUN = "short_run"  # Short Run (utility)
    TSIGNALS = "tsignals"  # Trend Signals (multi-output)
    TTM_TREND = "ttm_trend"  # TTM Trend
    VHF = "vhf"            # Vertical Horizontal Filter
    VORTEX = "vortex"      # Vortex (multi-output: vip, vim)
    XSIGNALS = "xsignals"  # Cross Signals (multi-output)
    
    # =========================================================================
    # STATISTICS INDICATORS (10)
    # =========================================================================
    ENTROPY = "entropy"        # Entropy
    KURTOSIS = "kurtosis"      # Kurtosis
    MAD = "mad"                # Mean Absolute Deviation
    MEDIAN = "median"          # Median
    QUANTILE = "quantile"      # Quantile
    SKEW = "skew"              # Skew
    STDEV = "stdev"            # Standard Deviation
    TOS_STDEVALL = "tos_stdevall"  # ThinkOrSwim Standard Deviation All (multi-output)
    VARIANCE = "variance"      # Variance
    ZSCORE = "zscore"          # Z Score
    
    # =========================================================================
    # PERFORMANCE INDICATORS (3)
    # =========================================================================
    DRAWDOWN = "drawdown"          # Drawdown (multi-output)
    LOG_RETURN = "log_return"      # Log Return
    PERCENT_RETURN = "percent_return"  # Percent Return
    
    # =========================================================================
    # CYCLES INDICATORS (2)
    # =========================================================================
    DSP = "dsp"            # Dominant Spectral Period
    EBSW = "ebsw"          # Even Better Sine Wave
    
    # =========================================================================
    # CANDLES INDICATORS (5)
    # =========================================================================
    CDL_DOJI = "cdl_doji"      # Doji Pattern
    CDL_INSIDE = "cdl_inside"  # Inside Bar Pattern
    CDL_PATTERN = "cdl_pattern"  # Candlestick Patterns (multi-output)
    CDL_Z = "cdl_z"            # Candle Z-Score (multi-output)
    HA = "ha"                  # Heikin-Ashi (multi-output: open, high, low, close)


# Multi-output indicator output names
# Maps IndicatorType to tuple of output suffixes that will be appended to output_key
MULTI_OUTPUT_KEYS: Dict[IndicatorType, Tuple[str, ...]] = {
    # Momentum
    IndicatorType.BRAR: ("ar", "br"),
    IndicatorType.DM: ("dmp", "dmn"),
    IndicatorType.ERI: ("bull", "bear"),
    IndicatorType.FISHER: ("fisher", "signal"),
    IndicatorType.KDJ: ("k", "d", "j"),
    IndicatorType.KST: ("kst", "signal"),
    IndicatorType.MACD: ("macd", "signal", "histogram"),
    IndicatorType.PPO: ("ppo", "signal", "histogram"),
    IndicatorType.PVO: ("pvo", "signal", "histogram"),
    IndicatorType.QQE: ("qqe", "rsi_ma", "qqe_long", "qqe_short"),
    IndicatorType.RVGI: ("rvgi", "signal"),
    IndicatorType.SMI: ("smi", "signal"),
    IndicatorType.SQUEEZE: ("sqz", "sqz_on", "sqz_off", "no_sqz"),
    IndicatorType.SQUEEZE_PRO: ("sqz", "sqz_on", "sqz_off", "no_sqz", "sqz_wide", "sqz_normal", "sqz_narrow"),
    IndicatorType.STC: ("stc", "macd", "stoch"),
    IndicatorType.STOCH: ("k", "d"),
    IndicatorType.STOCHRSI: ("k", "d"),
    IndicatorType.TRIX: ("trix", "signal"),
    IndicatorType.TSI: ("tsi", "signal"),
    IndicatorType.VWMACD: ("vwmacd", "signal", "histogram"),
    
    # Overlap
    IndicatorType.HILO: ("hilo", "hilos"),
    IndicatorType.ICHIMOKU: ("isa", "isb", "its", "iks", "ics"),
    IndicatorType.LINREG: ("lr", "slope", "intercept", "r", "stderr"),
    IndicatorType.SUPERTREND: ("trend", "direction", "long", "short"),
    
    # Volatility
    IndicatorType.ABERRATION: ("atr", "zg", "sg", "xg"),
    IndicatorType.ACCBANDS: ("lower", "mid", "upper"),
    IndicatorType.BBANDS: ("lower", "mid", "upper", "bandwidth", "percent_b"),
    IndicatorType.DONCHIAN: ("lower", "mid", "upper"),
    IndicatorType.HWC: ("lower", "mid", "upper"),
    IndicatorType.KC: ("lower", "basis", "upper"),
    IndicatorType.THERMO: ("thermo", "ma", "long", "short"),
    
    # Volume
    IndicatorType.AOBV: ("obv", "obv_min", "obv_max"),
    IndicatorType.KVO: ("kvo", "signal"),
    
    # Trend
    IndicatorType.ADX: ("adx", "dmp", "dmn"),
    IndicatorType.AMAT: ("amat_lr", "amat_sr"),
    IndicatorType.AROON: ("up", "down", "osc"),
    IndicatorType.CKSP: ("long", "short"),
    IndicatorType.PSAR: ("long", "short", "af", "reversal"),
    IndicatorType.VORTEX: ("vip", "vim"),
    
    # Statistics
    IndicatorType.TOS_STDEVALL: ("lower_1", "lower_2", "lower_3", "mid", "upper_1", "upper_2", "upper_3"),
    
    # Performance
    IndicatorType.DRAWDOWN: ("dd", "max_dd", "max_dd_pct"),
    
    # Candles
    IndicatorType.CDL_Z: ("open", "high", "low", "close"),
    IndicatorType.HA: ("open", "high", "low", "close"),
}


def is_multi_output(indicator_type: IndicatorType) -> bool:
    """Check if indicator type produces multiple outputs."""
    return indicator_type in MULTI_OUTPUT_KEYS


def get_output_names(indicator_type: IndicatorType) -> Tuple[str, ...]:
    """Get output names for an indicator type."""
    if indicator_type in MULTI_OUTPUT_KEYS:
        return MULTI_OUTPUT_KEYS[indicator_type]
    return ()  # Single-output indicators return empty tuple


class InputSource(str, Enum):
    """
    Data sources for indicator computation.
    
    OHLCV: Use the named price column directly
    INDICATOR: Use another indicator's output as input (for chained indicators)
    """
    OPEN = "open"
    HIGH = "high"
    LOW = "low"
    CLOSE = "close"
    VOLUME = "volume"
    # HLC3, OHLC4 computed from multiple columns
    HLC3 = "hlc3"      # (high + low + close) / 3
    OHLC4 = "ohlc4"    # (open + high + low + close) / 4
    # Reference another indicator output
    INDICATOR = "indicator"


@dataclass(frozen=True)
class FeatureSpec:
    """
    Specification for a single indicator/feature.
    
    Attributes:
        indicator_type: Type of indicator to compute
        output_key: Name of the output in FeedStore (for single-output) or prefix (for multi-output)
        params: Parameters for the indicator (e.g., {"length": 20})
        input_source: Data source for the indicator (default: close)
        input_indicator_key: If input_source=INDICATOR, the key of that indicator
        outputs: For multi-output indicators, mapping of standard name -> custom key
                 e.g., {"macd": "macd_12_26_9", "signal": "macd_signal"}
        description: Optional human-readable description
    
    Examples:
        # EMA 20 on close (single output)
        FeatureSpec(
            indicator_type=IndicatorType.EMA,
            output_key="ema_20",
            params={"length": 20},
            input_source=InputSource.CLOSE,
        )
        
        # MACD with custom output keys (multi-output)
        FeatureSpec(
            indicator_type=IndicatorType.MACD,
            output_key="macd",  # prefix
            params={"fast": 12, "slow": 26, "signal": 9},
            outputs={"macd": "macd_line", "signal": "macd_signal", "histogram": "macd_hist"},
        )
        
        # Bollinger Bands (multi-output with default keys)
        FeatureSpec(
            indicator_type=IndicatorType.BBANDS,
            output_key="bb",  # will generate bb_upper, bb_middle, bb_lower, etc.
            params={"length": 20, "std": 2.0},
        )
    """
    indicator_type: IndicatorType
    output_key: str
    params: Dict[str, Any] = field(default_factory=dict)
    input_source: InputSource = InputSource.CLOSE
    input_indicator_key: Optional[str] = None
    outputs: Optional[Dict[str, str]] = None
    description: Optional[str] = None
    
    def __post_init__(self):
        """Validate spec."""
        if not self.output_key:
            raise ValueError("output_key is required")
        
        # Validate indicator-specific requirements
        if self.indicator_type == IndicatorType.ATR:
            # ATR always uses HLC internally, input_source is ignored
            pass
        elif self.indicator_type in (IndicatorType.STOCH, IndicatorType.BBANDS):
            # These always use HLC/HLCV internally
            pass
        elif self.input_source == InputSource.INDICATOR:
            if not self.input_indicator_key:
                raise ValueError(
                    "input_indicator_key required when input_source=INDICATOR"
                )
        
        # Validate multi-output mapping if provided
        if self.outputs is not None and is_multi_output(self.indicator_type):
            valid_outputs = set(get_output_names(self.indicator_type))
            for key in self.outputs.keys():
                if key not in valid_outputs:
                    raise ValueError(
                        f"Invalid output '{key}' for {self.indicator_type.value}. "
                        f"Valid outputs: {valid_outputs}"
                    )
    
    @property
    def is_multi_output(self) -> bool:
        """Check if this spec produces multiple outputs."""
        return is_multi_output(self.indicator_type)
    
    @property
    def output_keys_list(self) -> List[str]:
        """
        Get all output keys this spec will produce.
        
        For single-output indicators, returns [output_key].
        For multi-output indicators, returns all output keys.
        """
        if not self.is_multi_output:
            return [self.output_key]
        
        output_names = get_output_names(self.indicator_type)
        if self.outputs:
            # Use custom mapping
            return [self.outputs.get(name, f"{self.output_key}_{name}") for name in output_names]
        else:
            # Use prefix_suffix pattern
            return [f"{self.output_key}_{name}" for name in output_names]
    
    def get_output_key(self, output_name: str) -> str:
        """
        Get the output key for a specific output name.
        
        Args:
            output_name: Standard output name (e.g., "macd", "signal")
            
        Returns:
            The key to use in FeedStore
        """
        if not self.is_multi_output:
            return self.output_key
        
        if self.outputs and output_name in self.outputs:
            return self.outputs[output_name]
        return f"{self.output_key}_{output_name}"
    
    @property
    def length(self) -> int:
        """Get the length/period parameter (most indicators use this)."""
        return self.params.get("length", 0)
    
    @property
    def warmup_bars(self) -> int:
        """
        Minimum bars needed for this indicator to produce valid values.
        
        Returns proper warmup for each indicator type:
        - EMA: 3x length for stabilization
        - SMA: length
        - RSI: length + 1
        - ATR: length + 1
        - MACD: 3x slow + signal
        - BBANDS: length
        - STOCH: k + smooth_k + d
        - STOCHRSI: rsi_length + length + max(k, d)
        """
        from ..indicator_vendor import (
            get_ema_warmup,
            get_sma_warmup,
            get_rsi_warmup,
            get_atr_warmup,
            get_macd_warmup,
            get_bbands_warmup,
            get_stoch_warmup,
            get_stochrsi_warmup,
        )
        
        ind_type = self.indicator_type
        
        if ind_type == IndicatorType.EMA:
            return get_ema_warmup(self.length)
        
        elif ind_type == IndicatorType.SMA:
            return get_sma_warmup(self.length)
        
        elif ind_type == IndicatorType.RSI:
            return get_rsi_warmup(self.length)
        
        elif ind_type == IndicatorType.ATR:
            return get_atr_warmup(self.length)
        
        elif ind_type == IndicatorType.MACD:
            fast = self.params.get("fast", 12)
            slow = self.params.get("slow", 26)
            signal = self.params.get("signal", 9)
            return get_macd_warmup(fast, slow, signal)
        
        elif ind_type == IndicatorType.BBANDS:
            return get_bbands_warmup(self.length)
        
        elif ind_type == IndicatorType.STOCH:
            k = self.params.get("k", 14)
            d = self.params.get("d", 3)
            smooth_k = self.params.get("smooth_k", 3)
            return get_stoch_warmup(k, d, smooth_k)
        
        elif ind_type == IndicatorType.STOCHRSI:
            length = self.params.get("length", 14)
            rsi_length = self.params.get("rsi_length", 14)
            k = self.params.get("k", 3)
            d = self.params.get("d", 3)
            return get_stochrsi_warmup(length, rsi_length, k, d)
        
        else:
            # Fallback for unknown types
            return self.length
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "indicator_type": self.indicator_type.value,
            "output_key": self.output_key,
            "params": self.params,
            "input_source": self.input_source.value,
            "input_indicator_key": self.input_indicator_key,
            "outputs": self.outputs,
            "description": self.description,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FeatureSpec":
        """Create from dict."""
        return cls(
            indicator_type=IndicatorType(d["indicator_type"]),
            output_key=d["output_key"],
            params=d.get("params", {}),
            input_source=InputSource(d.get("input_source", "close")),
            input_indicator_key=d.get("input_indicator_key"),
            outputs=d.get("outputs"),
            description=d.get("description"),
        )


@dataclass
class FeatureSpecSet:
    """
    Collection of FeatureSpecs for a single (symbol, tf) pair.
    
    Manages dependency ordering for chained indicators and provides
    validation that all required inputs are available.
    
    Attributes:
        symbol: Trading symbol
        tf: Timeframe string
        specs: List of FeatureSpecs (order matters for dependencies)
    """
    symbol: str
    tf: str
    specs: List[FeatureSpec] = field(default_factory=list)
    
    def __post_init__(self):
        """Validate specs."""
        self._validate_unique_keys()
        self._validate_dependencies()
    
    def _validate_unique_keys(self):
        """Ensure all output_keys are unique (including multi-output expansion)."""
        all_keys = []
        for spec in self.specs:
            all_keys.extend(spec.output_keys_list)
        
        if len(all_keys) != len(set(all_keys)):
            duplicates = [k for k in all_keys if all_keys.count(k) > 1]
            raise ValueError(f"Duplicate output_keys: {set(duplicates)}")
    
    def _validate_dependencies(self):
        """
        Ensure indicator dependencies are satisfied.
        
        An indicator with input_source=INDICATOR must reference
        an output_key that appears earlier in the specs list.
        """
        available_keys = set()
        for spec in self.specs:
            if spec.input_source == InputSource.INDICATOR:
                if spec.input_indicator_key not in available_keys:
                    raise ValueError(
                        f"Indicator '{spec.output_key}' depends on "
                        f"'{spec.input_indicator_key}' which is not defined earlier"
                    )
            # Add all output keys from this spec
            available_keys.update(spec.output_keys_list)
    
    def add(self, spec: FeatureSpec):
        """Add a spec to the set (validates dependencies)."""
        # Check for duplicate keys (including multi-output)
        existing_keys = set()
        for s in self.specs:
            existing_keys.update(s.output_keys_list)
        
        for key in spec.output_keys_list:
            if key in existing_keys:
                raise ValueError(f"Duplicate output_key: {key}")
        
        # Check dependency
        if spec.input_source == InputSource.INDICATOR:
            if spec.input_indicator_key not in existing_keys:
                raise ValueError(
                    f"Indicator '{spec.output_key}' depends on "
                    f"'{spec.input_indicator_key}' which is not defined"
                )
        
        self.specs.append(spec)
    
    @property
    def output_keys(self) -> List[str]:
        """Get all output keys (including multi-output expansion)."""
        keys = []
        for spec in self.specs:
            keys.extend(spec.output_keys_list)
        return keys
    
    @property
    def max_warmup_bars(self) -> int:
        """Get maximum warmup bars needed across all specs."""
        if not self.specs:
            return 0
        return max(s.warmup_bars for s in self.specs)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "symbol": self.symbol,
            "tf": self.tf,
            "specs": [s.to_dict() for s in self.specs],
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FeatureSpecSet":
        """Create from dict."""
        specs = [FeatureSpec.from_dict(s) for s in d.get("specs", [])]
        return cls(
            symbol=d["symbol"],
            tf=d["tf"],
            specs=specs,
        )


# ============================================================================
# Factory functions for common indicator specs
# ============================================================================

def ema_spec(output_key: str, length: int, source: InputSource = InputSource.CLOSE) -> FeatureSpec:
    """Create EMA spec with common defaults."""
    return FeatureSpec(
        indicator_type=IndicatorType.EMA,
        output_key=output_key,
        params={"length": length},
        input_source=source,
    )


def sma_spec(output_key: str, length: int, source: InputSource = InputSource.CLOSE) -> FeatureSpec:
    """Create SMA spec with common defaults."""
    return FeatureSpec(
        indicator_type=IndicatorType.SMA,
        output_key=output_key,
        params={"length": length},
        input_source=source,
    )


def rsi_spec(output_key: str, length: int = 14) -> FeatureSpec:
    """Create RSI spec with common defaults."""
    return FeatureSpec(
        indicator_type=IndicatorType.RSI,
        output_key=output_key,
        params={"length": length},
        input_source=InputSource.CLOSE,
    )


def atr_spec(output_key: str, length: int = 14) -> FeatureSpec:
    """Create ATR spec with common defaults."""
    return FeatureSpec(
        indicator_type=IndicatorType.ATR,
        output_key=output_key,
        params={"length": length},
    )


def macd_spec(
    output_key: str,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
    outputs: Optional[Dict[str, str]] = None,
) -> FeatureSpec:
    """
    Create MACD spec.
    
    Outputs: macd, signal, histogram
    Default keys: {output_key}_macd, {output_key}_signal, {output_key}_histogram
    
    Args:
        output_key: Prefix for output keys
        fast: Fast EMA period (default: 12)
        slow: Slow EMA period (default: 26)
        signal: Signal EMA period (default: 9)
        outputs: Optional custom output key mapping
    """
    return FeatureSpec(
        indicator_type=IndicatorType.MACD,
        output_key=output_key,
        params={"fast": fast, "slow": slow, "signal": signal},
        outputs=outputs,
    )


def bbands_spec(
    output_key: str,
    length: int = 20,
    std: float = 2.0,
    outputs: Optional[Dict[str, str]] = None,
) -> FeatureSpec:
    """
    Create Bollinger Bands spec.
    
    Outputs: upper, middle, lower, bandwidth, percent_b
    Default keys: {output_key}_upper, {output_key}_middle, etc.
    
    Args:
        output_key: Prefix for output keys
        length: SMA period (default: 20)
        std: Standard deviation multiplier (default: 2.0)
        outputs: Optional custom output key mapping
    """
    return FeatureSpec(
        indicator_type=IndicatorType.BBANDS,
        output_key=output_key,
        params={"length": length, "std": std},
        outputs=outputs,
    )


def stoch_spec(
    output_key: str,
    k: int = 14,
    d: int = 3,
    smooth_k: int = 3,
    outputs: Optional[Dict[str, str]] = None,
) -> FeatureSpec:
    """
    Create Stochastic Oscillator spec.
    
    Outputs: k, d
    Default keys: {output_key}_k, {output_key}_d
    
    Args:
        output_key: Prefix for output keys
        k: %K lookback period (default: 14)
        d: %D smoothing period (default: 3)
        smooth_k: %K smoothing period (default: 3)
        outputs: Optional custom output key mapping
    """
    return FeatureSpec(
        indicator_type=IndicatorType.STOCH,
        output_key=output_key,
        params={"k": k, "d": d, "smooth_k": smooth_k},
        outputs=outputs,
    )


def stochrsi_spec(
    output_key: str,
    length: int = 14,
    rsi_length: int = 14,
    k: int = 3,
    d: int = 3,
    outputs: Optional[Dict[str, str]] = None,
) -> FeatureSpec:
    """
    Create Stochastic RSI spec.
    
    Outputs: k, d
    Default keys: {output_key}_k, {output_key}_d
    
    Args:
        output_key: Prefix for output keys
        length: Stochastic lookback on RSI (default: 14)
        rsi_length: RSI period (default: 14)
        k: %K smoothing period (default: 3)
        d: %D smoothing period (default: 3)
        outputs: Optional custom output key mapping
    """
    return FeatureSpec(
        indicator_type=IndicatorType.STOCHRSI,
        output_key=output_key,
        params={"length": length, "rsi_length": rsi_length, "k": k, "d": d},
        outputs=outputs,
    )
