"""
System configuration loader.

Loads and validates YAML system configs from src/strategies/strategies/.
Resolves system_id + window_name to concrete run parameters.

Terminology model:
- StrategyFamily: Pure Python trading logic (strategy_id + strategy_version)
- StrategyInstance: One configured use of a StrategyFamily inside a System
- System: A configured trading robot with 1..N StrategyInstances
- Run: A single backtest execution of a System

Identifier model:
- Global (stable across runs):
  - strategy_id: stable family name (e.g., "ema_rsi_atr")
  - strategy_version: explicit version string (e.g., "1.0.0")
  - strategy_instance_id: unique within a system (e.g., "entry", "filter_high_tf")
  - system_id: human-readable unique name for the YAML
  - system_uid: deterministic hash of resolved config for lineage
- Instance (per-run):
  - run_id: unique ID for each execution
  - window_name: hygiene|test
"""

import json
import hashlib
from enum import Enum
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any

from typing import TYPE_CHECKING

from .types import WindowConfig
from .window_presets import get_window_preset, has_preset

if TYPE_CHECKING:
    from .feature_registry import FeatureRegistry


# Path to system configs directory
CONFIGS_DIR = Path(__file__).parent.parent / "strategies" / "configs"


# =============================================================================
# Mode Enums (Extension Points)
# =============================================================================
# These enums define the supported modes for this simulator version.
# Only implemented values are included; future modes are commented placeholders.

class MarginMode(Enum):
    """
    Margin mode enum (extension point for future modes).
    
    This simulator version supports ISOLATED only.
    Cross margin and portfolio margin will be added in future versions.
    """
    ISOLATED = "isolated"
    # CROSS = "cross"  # Future: not implemented
    # PORTFOLIO = "portfolio"  # Future: not implemented


class InstrumentType(Enum):
    """
    Instrument type enum (extension point for future modes).
    
    This simulator version supports PERP and LINEAR_PERP only.
    Spot and inverse instruments will be added in future versions.
    """
    PERP = "perp"
    LINEAR_PERP = "linear_perp"
    # SPOT = "spot"  # Future: not implemented
    # INVERSE = "inverse"  # Future: not implemented


# =============================================================================
# Mode Lock Validation Functions
# =============================================================================

def validate_usdt_pair(symbol: str) -> tuple[str, str]:
    """
    Validate and parse USDT-quoted perpetual pair.
    
    This simulator version supports USDT-quoted linear perpetuals only.
    Strict validation: must be exactly BASEUSDT format (no suffixes, separators, variations).
    
    Args:
        symbol: Trading symbol (e.g., "BTCUSDT", "ETHUSDT")
        
    Returns:
        Tuple of (base_currency, quote_currency)
        Example: ("BTC", "USDT")
        
    Raises:
        ValueError: If symbol is not a valid USDT-quoted perpetual
        
    Examples:
        >>> validate_usdt_pair("BTCUSDT")
        ("BTC", "USDT")
        >>> validate_usdt_pair("BTCUSD")  # Raises ValueError
        >>> validate_usdt_pair("BTCUSDC")  # Raises ValueError
        >>> validate_usdt_pair("BTC-USDT")  # Raises ValueError (separator)
        >>> validate_usdt_pair("BTCUSD_PERP")  # Raises ValueError (suffix)
    """
    if not symbol:
        raise ValueError(
            "Symbol is required. "
            "This simulator version supports USDT-quoted perpetuals only. "
            "Supported format: BASEUSDT (e.g., BTCUSDT, ETHUSDT)"
        )
    
    # Normalize symbol: uppercase, remove slashes only (keep other chars for validation)
    normalized = symbol.strip().upper().replace("/", "")
    
    # Must end with exactly USDT (not USDC, USD, etc.)
    if not normalized.endswith("USDT"):
        raise ValueError(
            f"Symbol '{symbol}' is not USDT-quoted. "
            f"This simulator version supports USDT-quoted perpetuals only. "
            f"Supported format: BASEUSDT (e.g., BTCUSDT, ETHUSDT)"
        )
    
    # Extract base and quote
    base = normalized[:-4]  # Everything except "USDT"
    quote = "USDT"
    
    # Validate base is not empty
    if not base:
        raise ValueError(
            f"Invalid symbol format: '{symbol}' (missing base currency). "
            f"Supported format: BASEUSDT (e.g., BTCUSDT, ETHUSDT)"
        )
    
    # Strict validation: base must be alphanumeric only (no special chars, separators)
    # This rejects: BTC-USDT (separator), BTCUSD_PERP (suffix), BTC.USDT (separator)
    if not base.isalnum():
        raise ValueError(
            f"Invalid base currency in symbol '{symbol}'. "
            f"Base currency must be alphanumeric only (no separators or special characters). "
            f"Supported format: BASEUSDT (e.g., BTCUSDT, ETHUSDT)"
        )
    
    return (base, quote)


def validate_margin_mode_isolated(margin_mode: str) -> None:
    """
    Validate that margin mode is isolated (this simulator version only).
    
    Args:
        margin_mode: Margin mode string from config
        
    Raises:
        ValueError: If margin_mode is not "isolated"
    """
    if margin_mode != MarginMode.ISOLATED.value:
        raise ValueError(
            f"Unsupported margin_mode='{margin_mode}'. "
            f"This simulator version supports 'isolated' margin mode only. "
            f"Cross margin and other modes will be added in future versions."
        )


def validate_quote_ccy_and_instrument_type(quote_ccy: str, instrument_type: str) -> None:
    """
    Validate quote currency and instrument type (this simulator version only).
    
    Args:
        quote_ccy: Quote currency string from config
        instrument_type: Instrument type string from config
        
    Raises:
        ValueError: If quote_ccy is not "USDT" or instrument_type is not supported
    """
    if quote_ccy != "USDT":
        raise ValueError(
            f"Unsupported quote_ccy='{quote_ccy}'. "
            f"This simulator version supports USDT-quoted pairs only."
        )
    
    valid_instrument_types = {InstrumentType.PERP.value, InstrumentType.LINEAR_PERP.value}
    if instrument_type not in valid_instrument_types:
        raise ValueError(
            f"Unsupported instrument_type='{instrument_type}'. "
            f"This simulator version supports 'perp' or 'linear_perp' only."
        )


@dataclass
class DataBuildConfig:
    """
    Dataset build configuration.

    The env field determines which DuckDB file is used:
    - "backtest": market_data_backtest.duckdb (default for backtests, uses live API data)
    - "live": market_data_live.duckdb (for live trading warm-up)
    - "demo": market_data_demo.duckdb (for paper trading)
    """
    env: str = "backtest"  # Default to backtest DB for historical simulations
    period: str = "3M"
    tfs: list[str] = field(default_factory=lambda: ["1h"])

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "env": self.env,
            "period": self.period,
            "tfs": sorted(self.tfs),
        }


@dataclass
class RiskProfileConfig:
    """
    Risk profile configuration for backtesting.
    
    Follows Bybit perpetual futures margin model (isolated, USDT linear):
    - Initial Margin (IM) = Position Value × initial_margin_rate
    - Maintenance Margin (MM) = Position Value × maintenance_margin_rate
    - Liquidation / account_blown when: Equity <= stop_equity_usdt
    - insufficient_free_margin when: free_margin < min_trade_usdt
    - Available Balance = max(0, Equity - Used Margin)
    
    Core fields:
    - initial_equity: Starting equity for backtest (in USDT, quote currency)
    - sizing_model: How to size trades ("percent_equity", "fixed_notional")
    - risk_per_trade_pct: Percent of equity to risk per trade
    - max_leverage: Maximum leverage allowed
    - min_trade_usdt: Minimum trade notional in USDT (for insufficient_free_margin check)
      All monetary values are in USDT.
    - stop_equity_usdt: Equity threshold for account_blown in USDT (default 0.0)
      All monetary values are in USDT.
    
    Margin model fields (Bybit-aligned):
    - initial_margin_rate: IMR as decimal (default derived from max_leverage if None)
    - maintenance_margin_rate: MMR as decimal (default 0.005 = 0.5%, Bybit lowest tier)
    - mark_price_source: Price source used as mark proxy for margining ("close" only in Phase 1)
    
    Fee model fields (Bybit perpetuals):
    - taker_fee_rate: Taker fee rate as decimal (default 0.00055 = 0.055%)
    - maker_fee_rate: Maker fee rate as decimal (default 0.0002 = 0.02%)
    - fee_mode: Fee mode ("taker_only" for MVP)
    
    Entry gate behavior:
    - include_est_close_fee_in_entry_gate: If True, entry gate includes estimated close fee
    
    Mode locks (this simulator version only):
    - margin_mode: Margin mode ("isolated" only for this version)
    - position_mode: Position mode ("oneway" only for this version)
    - quote_ccy: Quote currency ("USDT" only for this version)
    - instrument_type: Instrument type ("perp" or "linear_perp" for this version)
    
    These mode locks are validated at config load time. Future versions will support
    cross margin, hedge mode, and other quote currencies.
    """
    # Core fields (initial_equity is REQUIRED - no default)
    initial_equity: float  # REQUIRED: Must be explicitly passed, no default
    sizing_model: str = "percent_equity"
    risk_per_trade_pct: float = 1.0
    max_leverage: float = 2.0
    max_drawdown_pct: float = 100.0  # Max allowed drawdown percentage (for state tracking)
    min_trade_usdt: float = 1.0
    stop_equity_usdt: float = 0.0

    # Position sizing caps (Bybit-aligned)
    # max_position_equity_pct: Maximum position size as % of equity (prevents 100% exposure)
    # reserve_fee_buffer: Reserve balance for entry+exit fees
    max_position_equity_pct: float = 95.0  # Leave 5% buffer for fees/safety
    reserve_fee_buffer: bool = True  # Reserve balance for fees

    # SL vs Liquidation safety check
    # Validates that stop-loss triggers before liquidation price
    # "reject": Reject entry if SL beyond liquidation price (default, safest)
    # "adjust": Auto-tighten SL to safe distance from liquidation
    # "warn": Allow entry but log warning
    on_sl_beyond_liq: str = "reject"

    # Margin model fields
    _initial_margin_rate: float | None = None  # If None, derived from max_leverage
    maintenance_margin_rate: float = 0.005  # 0.5% - Bybit lowest tier default
    mm_deduction: float = 0.0  # Bybit mmDeduction (0 for tier 1)
    mark_price_source: str = "close"

    # Fee model fields (loaded from DEFAULTS if None)
    taker_fee_rate: float | None = None
    maker_fee_rate: float | None = None
    fee_mode: str = "taker_only"  # MVP: only taker fees applied
    
    # Entry gate behavior
    include_est_close_fee_in_entry_gate: bool = False
    
    # Mode locks (this simulator version only)
    margin_mode: str = "isolated"  # Isolated only for this version
    position_mode: str = "oneway"  # One-way only for this version (no hedge)
    quote_ccy: str = "USDT"  # USDT-quoted pairs only for this version
    instrument_type: str = "perp"  # Perpetual contracts only for this version

    # Valid values for mode locks (Phase 1 restrictions)
    _VALID_MARK_PRICE_SOURCES = ("close",)
    _VALID_FEE_MODES = ("taker_only",)
    _VALID_MARGIN_MODES = ("isolated",)
    _VALID_POSITION_MODES = ("oneway",)
    _VALID_SL_LIQ_MODES = ("reject", "adjust", "warn")

    def __post_init__(self) -> None:
        """Validate config fields at load time (fail-loud)."""
        # Load fee defaults from config/defaults.yml if not specified
        from src.config.constants import DEFAULTS
        if self.taker_fee_rate is None:
            object.__setattr__(self, 'taker_fee_rate', DEFAULTS.fees.taker_rate)
        if self.maker_fee_rate is None:
            object.__setattr__(self, 'maker_fee_rate', DEFAULTS.fees.maker_rate)

        # Validate mark_price_source
        if self.mark_price_source not in self._VALID_MARK_PRICE_SOURCES:
            raise ValueError(
                f"Invalid mark_price_source='{self.mark_price_source}'. "
                f"Phase 1 supports only: {self._VALID_MARK_PRICE_SOURCES}"
            )

        # Validate fee_mode
        if self.fee_mode not in self._VALID_FEE_MODES:
            raise ValueError(
                f"Invalid fee_mode='{self.fee_mode}'. "
                f"MVP supports only: {self._VALID_FEE_MODES}"
            )

        # Validate margin_mode
        if self.margin_mode not in self._VALID_MARGIN_MODES:
            raise ValueError(
                f"Invalid margin_mode='{self.margin_mode}'. "
                f"This simulator version supports only: {self._VALID_MARGIN_MODES}"
            )

        # Validate position_mode
        if self.position_mode not in self._VALID_POSITION_MODES:
            raise ValueError(
                f"Invalid position_mode='{self.position_mode}'. "
                f"This simulator version supports only: {self._VALID_POSITION_MODES}"
            )

        # Validate on_sl_beyond_liq
        if self.on_sl_beyond_liq not in self._VALID_SL_LIQ_MODES:
            raise ValueError(
                f"Invalid on_sl_beyond_liq='{self.on_sl_beyond_liq}'. "
                f"Valid values: {self._VALID_SL_LIQ_MODES}"
            )

    @property
    def initial_margin_rate(self) -> float:
        """
        Initial margin rate.
        
        If explicitly set, returns that value.
        Otherwise, derived as 1 / max_leverage.
        """
        if self._initial_margin_rate is not None:
            return self._initial_margin_rate
        return 1.0 / self.max_leverage
    
    @initial_margin_rate.setter
    def initial_margin_rate(self, value: float | None) -> None:
        """Set explicit initial margin rate."""
        self._initial_margin_rate = value
    
    @property
    def leverage(self) -> float:
        """
        Effective leverage derived from initial_margin_rate.
        
        leverage = 1 / initial_margin_rate
        """
        return 1.0 / self.initial_margin_rate
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            # Core
            "initial_equity": self.initial_equity,
            "sizing_model": self.sizing_model,
            "risk_per_trade_pct": self.risk_per_trade_pct,
            "max_leverage": self.max_leverage,
            "max_drawdown_pct": self.max_drawdown_pct,
            "min_trade_usdt": self.min_trade_usdt,
            "stop_equity_usdt": self.stop_equity_usdt,
            # Position sizing caps
            "max_position_equity_pct": self.max_position_equity_pct,
            "reserve_fee_buffer": self.reserve_fee_buffer,
            # Margin model
            "initial_margin_rate": self.initial_margin_rate,
            "maintenance_margin_rate": self.maintenance_margin_rate,
            "mark_price_source": self.mark_price_source,
            # Fee model
            "taker_fee_rate": self.taker_fee_rate,
            "maker_fee_rate": self.maker_fee_rate,
            "fee_mode": self.fee_mode,
            # Entry gate
            "include_est_close_fee_in_entry_gate": self.include_est_close_fee_in_entry_gate,
            # Mode locks
            "margin_mode": self.margin_mode,
            "position_mode": self.position_mode,
            "quote_ccy": self.quote_ccy,
            "instrument_type": self.instrument_type,
            # SL vs Liquidation
            "on_sl_beyond_liq": self.on_sl_beyond_liq,
            # Derived
            "leverage": self.leverage,
        }


def resolve_risk_profile(
    base: RiskProfileConfig,
    overrides: dict[str, Any] | None = None,
) -> RiskProfileConfig:
    """
    Merge CLI overrides into a base risk profile.
    
    Args:
        base: Base risk profile from YAML
        overrides: Optional dict with keys like:
            - 'initial_equity', 'risk_per_trade_pct', 'max_leverage'
            - 'min_trade_usdt', 'stop_equity_usdt'
            - 'initial_margin_rate', 'maintenance_margin_rate', 'mark_price_source'
            - 'taker_fee_rate', 'maker_fee_rate', 'fee_mode'
            - 'include_est_close_fee_in_entry_gate'
        
    Returns:
        New RiskProfileConfig with overrides applied
    """
    if not overrides:
        return base
    
    # Handle initial_margin_rate override
    imr_override = overrides.get("initial_margin_rate")
    imr_value = float(imr_override) if imr_override is not None else base._initial_margin_rate
    
    # Handle maker_fee_rate (can be None)
    maker_fee = overrides.get("maker_fee_rate", base.maker_fee_rate)
    if maker_fee is not None:
        maker_fee = float(maker_fee)
    
    result = RiskProfileConfig(
        # Core
        initial_equity=float(overrides.get("initial_equity", base.initial_equity)),
        sizing_model=overrides.get("sizing_model", base.sizing_model),
        risk_per_trade_pct=float(overrides.get("risk_per_trade_pct", base.risk_per_trade_pct)),
        max_leverage=float(overrides.get("max_leverage", base.max_leverage)),
        max_drawdown_pct=float(overrides.get("max_drawdown_pct", base.max_drawdown_pct)),
        min_trade_usdt=float(overrides.get("min_trade_usdt", base.min_trade_usdt)),
        stop_equity_usdt=float(overrides.get("stop_equity_usdt", base.stop_equity_usdt)),
        # Margin model
        _initial_margin_rate=imr_value,
        maintenance_margin_rate=float(overrides.get("maintenance_margin_rate", base.maintenance_margin_rate)),
        mark_price_source=str(overrides.get("mark_price_source", base.mark_price_source)),
        # Fee model
        taker_fee_rate=float(overrides.get("taker_fee_rate", base.taker_fee_rate)),
        maker_fee_rate=maker_fee,
        fee_mode=str(overrides.get("fee_mode", base.fee_mode)),
        # Entry gate
        include_est_close_fee_in_entry_gate=bool(
            overrides.get("include_est_close_fee_in_entry_gate", base.include_est_close_fee_in_entry_gate)
        ),
        # Mode locks (carry from base, typically not overridden)
        margin_mode=str(overrides.get("margin_mode", base.margin_mode)),
        position_mode=str(overrides.get("position_mode", base.position_mode)),
        quote_ccy=str(overrides.get("quote_ccy", base.quote_ccy)),
        instrument_type=str(overrides.get("instrument_type", base.instrument_type)),
        # SL vs Liquidation safety
        on_sl_beyond_liq=str(overrides.get("on_sl_beyond_liq", base.on_sl_beyond_liq)),
    )

    return result


@dataclass
class StrategyInstanceInputs:
    """Input configuration for a StrategyInstance (symbol/tf/feed alias)."""
    symbol: str = ""
    tf: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "symbol": self.symbol,
            "tf": self.tf,
        }


@dataclass
class StrategyInstanceConfig:
    """
    Configuration for a single StrategyInstance within a System.
    
    A StrategyInstance is one configured use of a StrategyFamily.
    It has its own inputs (symbol/tf), params, and optional role.
    """
    # Identity
    strategy_instance_id: str
    strategy_id: str
    strategy_version: str = "1.0.0"
    
    # Inputs (which data feed this instance consumes)
    inputs: StrategyInstanceInputs = field(default_factory=StrategyInstanceInputs)

    # Instance-specific parameters
    params: dict[str, Any] = field(default_factory=dict)

    # Optional role tag (e.g., "entry", "filter", "exit")
    role: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        result = {
            "strategy_instance_id": self.strategy_instance_id,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "inputs": self.inputs.to_dict(),
            "params": dict(sorted(self.params.items())),
        }
        if self.role:
            result["role"] = self.role
        return result


@dataclass
class SystemConfig:
    """
    Complete system configuration for backtesting.
    
    A System is a configured trading robot containing:
    - One or more StrategyInstances
    - Risk profile and mode
    - Windows (hygiene/test)
    - Data build settings
    
    Identifiers:
    - system_id: Human-readable unique name for the YAML config
    - system_uid: Deterministic hash of resolved config (computed after load)
    - primary_strategy_instance_id: Which StrategyInstance is the primary (executed in Phase 1)
    """
    # Identity
    system_id: str
    
    # Primary symbol/tf for the system (for routing/display)
    symbol: str = ""
    tf: str = ""

    # Description for UI display (from Play.description)
    description: str = ""

    # Execution timeframe (master clock for stepping)
    # If None, defaults to tf (low_tf)
    exec_tf: str | None = None

    # Strategy instances (1..N)
    strategies: list[StrategyInstanceConfig] = field(default_factory=list)
    primary_strategy_instance_id: str = ""

    # Windows (raw from YAML)
    windows: dict[str, dict[str, str]] = field(default_factory=dict)
    
    # Risk configuration
    risk_profile: RiskProfileConfig = field(default_factory=lambda: RiskProfileConfig(initial_equity=0.0))
    risk_mode: str = "none"  # "none" or "rules"
    
    # Data build settings
    data_build: DataBuildConfig = field(default_factory=DataBuildConfig)

    # Play-declared warmup bars per TF role (low_tf/med_tf/high_tf)
    # This is the CANONICAL warmup source - engine MUST use this, not recompute
    # MUST NOT be empty - engine will fail loud if missing (no fallback path)
    warmup_bars_by_role: dict[str, int] = field(default_factory=dict)

    # Play-declared delay bars per TF role (low_tf/med_tf/high_tf)
    # Delay = bars to skip at evaluation start (no-lookahead guarantee)
    # Engine MUST fail loud if this is missing when Play declares market_structure
    delay_bars_by_role: dict[str, int] = field(default_factory=dict)

    # Play feature specs by role (low_tf/med_tf/high_tf)
    # Required for indicator computation - no legacy params support
    feature_specs_by_role: dict[str, list[Any]] = field(default_factory=dict)

    # Play required indicators by role (low_tf/med_tf/high_tf)
    # Used by find_first_valid_bar to avoid requiring mutually exclusive outputs
    # (e.g., PSAR long/short or SuperTrend long/short)
    required_indicators_by_role: dict[str, list[str]] = field(default_factory=dict)

    # ==========================================================================
    # Feature Registry Architecture (replaces role-based approach)
    # ==========================================================================

    # FeatureRegistry from Play (unified indicator/structure access)
    # When set, this is the canonical source for features, warmup, and TFs
    feature_registry: "FeatureRegistry | None" = None

    # Warmup bars keyed by TF string (e.g., {"15m": 50, "1h": 200})
    # Used with Feature Registry architecture - replaces warmup_bars_by_role
    warmup_by_tf: dict[str, int] = field(default_factory=dict)

    # Computed after load (not from YAML)
    _system_uid: str = field(default="", repr=False)
    
    def __post_init__(self):
        """Compute system_uid after initialization."""
        if not self._system_uid:
            self._system_uid = self._compute_uid()
    
    @property
    def system_uid(self) -> str:
        """
        Deterministic hash of the resolved system config.
        
        Provides immutable lineage even if YAML file changes later.
        Includes: symbol, tf, strategies, windows, risk_profile, risk_mode, data_build.
        """
        if not self._system_uid:
            self._system_uid = self._compute_uid()
        return self._system_uid
    
    def _compute_uid(self) -> str:
        """Compute deterministic hash from canonical config dict."""
        canonical = self.to_canonical_dict()
        json_str = json.dumps(canonical, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(json_str.encode('utf-8')).hexdigest()[:16]
    
    def to_canonical_dict(self) -> dict[str, Any]:
        """
        Convert to canonical dict for fingerprinting.
        
        Sorted keys, deterministic serialization.
        Excludes system_id (the human name) since the hash IS the identity.
        Strategies are sorted by strategy_instance_id for deterministic hashing.
        """
        # Sort windows
        sorted_windows = {}
        for wname in sorted(self.windows.keys()):
            sorted_windows[wname] = dict(sorted(self.windows[wname].items()))
        
        # Sort strategies by instance_id for deterministic hash
        sorted_strategies = sorted(
            [s.to_dict() for s in self.strategies],
            key=lambda s: s["strategy_instance_id"]
        )
        
        return {
            "symbol": self.symbol,
            "tf": self.tf,
            "exec_tf": self.resolved_exec_tf,
            "primary_strategy_instance_id": self.primary_strategy_instance_id,
            "strategies": sorted_strategies,
            "windows": sorted_windows,
            "risk_profile": self.risk_profile.to_dict(),
            "risk_mode": self.risk_mode,
            "data_build": self.data_build.to_dict(),
            "warmup_bars_by_role": self.warmup_bars_by_role,
            "delay_bars_by_role": self.delay_bars_by_role,
        }
    
    def get_primary_strategy(self) -> StrategyInstanceConfig:
        """
        Get the primary StrategyInstance.
        
        Returns:
            The StrategyInstance with id == primary_strategy_instance_id
            
        Raises:
            ValueError: If primary strategy not found
        """
        for s in self.strategies:
            if s.strategy_instance_id == self.primary_strategy_instance_id:
                return s
        raise ValueError(
            f"Primary strategy '{self.primary_strategy_instance_id}' not found in strategies. "
            f"Available: {[s.strategy_instance_id for s in self.strategies]}"
        )
    
    @property
    def strategy_id(self) -> str:
        """Get the primary strategy's strategy_id (for convenience)."""
        return self.get_primary_strategy().strategy_id
    
    @property
    def strategy_version(self) -> str:
        """Get the primary strategy's strategy_version (for convenience)."""
        return self.get_primary_strategy().strategy_version
    
    @property
    def params(self) -> dict[str, Any]:
        """Get the primary strategy's params (for convenience)."""
        return self.get_primary_strategy().params
    
    @property
    def resolved_exec_tf(self) -> str:
        """
        Get the resolved execution timeframe.
        
        Returns exec_tf if explicitly set, otherwise defaults to tf (low_tf).
        """
        return self.exec_tf if self.exec_tf else self.tf
    
    def get_window(self, window_name: str) -> WindowConfig:
        """
        Resolve a window name to start/end datetimes.
        
        Supports two modes:
        1. Preset reference: windows.<name>.preset -> resolved via window_presets module
        2. Explicit dates: windows.<name>.start + windows.<name>.end
        
        Args:
            window_name: "hygiene" or "test"
            
        Returns:
            WindowConfig with resolved datetimes
            
        Raises:
            ValueError: If window_name not found or invalid
        """
        if window_name not in self.windows:
            available = list(self.windows.keys())
            raise ValueError(
                f"Window '{window_name}' not found in system '{self.system_id}'. "
                f"Available: {available}"
            )
        
        window_data = self.windows[window_name]
        
        # Check for preset reference first
        preset_name = window_data.get("preset")
        if preset_name:
            # Resolve preset via window_presets module
            start, end = get_window_preset(self.symbol, self.tf, preset_name)
            return WindowConfig(
                window_name=window_name,
                start=start,
                end=end,
            )
        
        # Fall back to explicit dates
        start_str = window_data.get("start", "")
        end_str = window_data.get("end", "")
        
        if not start_str or not end_str:
            raise ValueError(
                f"Window '{window_name}' missing start/end dates and no preset specified"
            )
        
        # Parse ISO date strings
        start = datetime.fromisoformat(start_str)
        end = datetime.fromisoformat(end_str)
        
        return WindowConfig(
            window_name=window_name,
            start=start,
            end=end,
        )
    
    def validate(self) -> list[str]:
        """
        Validate the configuration.
        
        Returns:
            List of error messages (empty if valid)
        """
        errors = []
        
        if not self.system_id:
            errors.append("system_id is required")
        if not self.symbol:
            errors.append("symbol is required")
        if not self.tf:
            errors.append("tf is required")
        if not self.strategies:
            errors.append("strategies list is required and must not be empty")
        if not self.primary_strategy_instance_id:
            errors.append("primary_strategy_instance_id is required")
        if not self.windows:
            errors.append("windows section is required")
        if self.risk_mode not in ("none", "rules"):
            errors.append(f"risk_mode must be 'none' or 'rules', got '{self.risk_mode}'")
        
        # Validate primary strategy exists
        if self.strategies and self.primary_strategy_instance_id:
            ids = [s.strategy_instance_id for s in self.strategies]
            if self.primary_strategy_instance_id not in ids:
                errors.append(
                    f"primary_strategy_instance_id '{self.primary_strategy_instance_id}' "
                    f"not found in strategies. Available: {ids}"
                )
            
            # Validate unique strategy_instance_ids
            if len(ids) != len(set(ids)):
                errors.append("strategy_instance_id values must be unique within a system")
        
        # Validate each strategy instance
        for s in self.strategies:
            if not s.strategy_instance_id:
                errors.append("Each strategy must have a strategy_instance_id")
            if not s.strategy_id:
                errors.append(f"Strategy '{s.strategy_instance_id}' missing strategy_id")
        
        # Validate windows have required dates OR a valid preset
        for window_name, window_data in self.windows.items():
            preset_name = window_data.get("preset")
            has_start = "start" in window_data
            has_end = "end" in window_data
            
            if preset_name:
                # Preset reference - validate it exists
                if not has_preset(self.symbol, self.tf, preset_name):
                    errors.append(
                        f"Window '{window_name}' references unknown preset '{preset_name}' "
                        f"for {self.symbol} {self.tf}"
                    )
            else:
                # Explicit dates required
                if not has_start:
                    errors.append(f"Window '{window_name}' missing 'start' date (and no preset)")
                if not has_end:
                    errors.append(f"Window '{window_name}' missing 'end' date (and no preset)")
        
        return errors