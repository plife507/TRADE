"""
CLI Wrapper for IdeaCard-based backtests.

This is the GOLDEN PATH for backtest execution:
CLI (trade_cli.py subcommands) → this wrapper → domain (engine/data)

All backtest validation, including smoke tests, should call this wrapper.
No ad-hoc test harnesses that re-implement pipeline logic.

Responsibilities:
- env validation (live|demo) + resolved DuckDB path + table name
- symbol normalization (uppercase + USDT-pair validation)
- timeframe validation (canonical: 1m/5m/15m/1h/4h/1d)
- tz normalization (strip tzinfo for DuckDB UTC-naive storage)
- window correctness (requested vs effective with warmup)
- coverage check against DuckDB
- indicator key printing (exec/htf/mtf)
- strict error messages (missing key vs NaN cause)
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Set
import traceback

import pandas as pd

from .shared import ToolResult
from ..config.constants import (
    DataEnv,
    DEFAULT_DATA_ENV,
    validate_data_env,
    validate_symbol,
    resolve_db_path,
    resolve_table_name,
)
from ..data.historical_data_store import (
    get_historical_store,
    TIMEFRAMES as DB_TIMEFRAMES,
    TF_MINUTES,
)
from ..backtest.idea_card import load_idea_card, list_idea_cards, IdeaCard
from ..backtest.execution_validation import (
    validate_idea_card_full,
    compute_warmup_requirements,
    get_declared_features_by_role,
    adapt_idea_card_to_system_config,
)
from ..backtest.indicators import get_required_indicator_columns_from_specs
from ..backtest.system_config import validate_usdt_pair
from ..utils.logger import get_logger


logger = get_logger()


# =============================================================================
# Canonical Timeframe Validation
# =============================================================================

# Canonical timeframes accepted by CLI (stored in DuckDB as-is)
CANONICAL_TIMEFRAMES = {"1m", "5m", "15m", "1h", "4h", "1d"}

# Bybit API intervals (NOT accepted - user must use canonical)
BYBIT_API_INTERVALS = {"1", "5", "15", "60", "240", "D"}

# Mapping from Bybit API interval to canonical
BYBIT_TO_CANONICAL = {
    "1": "1m",
    "5": "5m",
    "15": "15m",
    "60": "1h",
    "240": "4h",
    "D": "1d",
}


def validate_canonical_tf(tf: str) -> str:
    """
    Validate timeframe is canonical format.
    
    Args:
        tf: Timeframe string (e.g., "1h", "15m")
        
    Returns:
        Validated canonical tf string
        
    Raises:
        ValueError: If tf is not canonical (with fix-it message)
    """
    tf_lower = tf.lower().strip()
    
    if tf_lower in CANONICAL_TIMEFRAMES:
        return tf_lower
    
    # Check if it's a Bybit API interval
    if tf in BYBIT_API_INTERVALS:
        canonical = BYBIT_TO_CANONICAL.get(tf, tf)
        raise ValueError(
            f"Timeframe '{tf}' is a Bybit API interval, not canonical. "
            f"Use '{canonical}' instead. "
            f"Canonical timeframes: {sorted(CANONICAL_TIMEFRAMES)}"
        )
    
    raise ValueError(
        f"Invalid timeframe: '{tf}'. "
        f"Must be one of: {sorted(CANONICAL_TIMEFRAMES)}"
    )


def normalize_timestamp(dt: datetime) -> datetime:
    """
    Normalize timestamp to UTC-naive for DuckDB storage.
    
    DuckDB stores timestamps as UTC-naive. If user passes tz-aware datetime,
    we strip the timezone info and log the normalization.
    
    Args:
        dt: Datetime (may be tz-aware)
        
    Returns:
        UTC-naive datetime
    """
    if dt.tzinfo is not None:
        # Convert to UTC first if needed, then strip
        try:
            dt_utc = dt.utctimetuple()
            dt = datetime(*dt_utc[:6])
        except Exception:
            # Just strip tzinfo if conversion fails
            dt = dt.replace(tzinfo=None)
        logger.info(f"Normalized tz-aware timestamp to UTC-naive: {dt}")
    return dt


# =============================================================================
# Preflight Result
# =============================================================================

@dataclass
class PreflightDiagnostics:
    """Diagnostics from preflight check."""
    # Environment
    env: str
    db_path: str
    ohlcv_table: str
    
    # Symbol/TF
    symbol: str
    exec_tf: str
    htf: Optional[str] = None
    mtf: Optional[str] = None
    
    # Window
    requested_start: Optional[datetime] = None
    requested_end: Optional[datetime] = None
    effective_start: Optional[datetime] = None  # includes warmup
    effective_end: Optional[datetime] = None
    warmup_bars: int = 0
    warmup_span_minutes: int = 0
    
    # Coverage
    db_earliest: Optional[datetime] = None
    db_latest: Optional[datetime] = None
    db_bar_count: int = 0
    has_sufficient_coverage: bool = False
    coverage_issue: Optional[str] = None
    
    # Indicator keys (declared)
    declared_keys_exec: List[str] = field(default_factory=list)
    declared_keys_htf: List[str] = field(default_factory=list)
    declared_keys_mtf: List[str] = field(default_factory=list)
    
    # Indicator keys (expanded, including multi-output suffixes)
    expanded_keys_exec: List[str] = field(default_factory=list)
    expanded_keys_htf: List[str] = field(default_factory=list)
    expanded_keys_mtf: List[str] = field(default_factory=list)
    
    # Validation
    idea_card_valid: bool = False
    idea_card_hash: Optional[str] = None
    validation_errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "env": self.env,
            "db_path": self.db_path,
            "ohlcv_table": self.ohlcv_table,
            "symbol": self.symbol,
            "exec_tf": self.exec_tf,
            "htf": self.htf,
            "mtf": self.mtf,
            "requested_start": self.requested_start.isoformat() if self.requested_start else None,
            "requested_end": self.requested_end.isoformat() if self.requested_end else None,
            "effective_start": self.effective_start.isoformat() if self.effective_start else None,
            "effective_end": self.effective_end.isoformat() if self.effective_end else None,
            "warmup_bars": self.warmup_bars,
            "warmup_span_minutes": self.warmup_span_minutes,
            "db_earliest": self.db_earliest.isoformat() if self.db_earliest else None,
            "db_latest": self.db_latest.isoformat() if self.db_latest else None,
            "db_bar_count": self.db_bar_count,
            "has_sufficient_coverage": self.has_sufficient_coverage,
            "coverage_issue": self.coverage_issue,
            "declared_keys_exec": self.declared_keys_exec,
            "declared_keys_htf": self.declared_keys_htf,
            "declared_keys_mtf": self.declared_keys_mtf,
            "expanded_keys_exec": self.expanded_keys_exec,
            "expanded_keys_htf": self.expanded_keys_htf,
            "expanded_keys_mtf": self.expanded_keys_mtf,
            "idea_card_valid": self.idea_card_valid,
            "idea_card_hash": self.idea_card_hash,
            "validation_errors": self.validation_errors,
        }
    
    def format_summary(self) -> str:
        """Format a human-readable summary for CLI output."""
        lines = []
        lines.append(f"Environment: {self.env}")
        lines.append(f"Database: {self.db_path}")
        lines.append(f"OHLCV Table: {self.ohlcv_table}")
        lines.append(f"Symbol: {self.symbol}")
        lines.append(f"Exec TF: {self.exec_tf}")
        if self.htf:
            lines.append(f"HTF: {self.htf}")
        if self.mtf:
            lines.append(f"MTF: {self.mtf}")
        lines.append("")
        lines.append("Window:")
        if self.requested_start:
            lines.append(f"  Requested: {self.requested_start.strftime('%Y-%m-%d %H:%M')} -> {self.requested_end.strftime('%Y-%m-%d %H:%M') if self.requested_end else 'now'}")
        if self.effective_start:
            lines.append(f"  Effective (with warmup): {self.effective_start.strftime('%Y-%m-%d %H:%M')} -> {self.effective_end.strftime('%Y-%m-%d %H:%M') if self.effective_end else 'now'}")
        lines.append(f"  Warmup: {self.warmup_bars} bars ({self.warmup_span_minutes} minutes)")
        lines.append("")
        lines.append("DB Coverage:")
        if self.db_earliest and self.db_latest:
            lines.append(f"  Range: {self.db_earliest.strftime('%Y-%m-%d %H:%M')} -> {self.db_latest.strftime('%Y-%m-%d %H:%M')}")
            lines.append(f"  Bars: {self.db_bar_count:,}")
        else:
            lines.append("  No data found")
        lines.append(f"  Sufficient: {'Yes' if self.has_sufficient_coverage else 'No'}")
        if self.coverage_issue:
            lines.append(f"  Issue: {self.coverage_issue}")
        lines.append("")
        lines.append("Declared Indicator Keys:")
        lines.append(f"  exec: {self.declared_keys_exec or '(none)'}")
        if self.declared_keys_htf:
            lines.append(f"  htf: {self.declared_keys_htf}")
        if self.declared_keys_mtf:
            lines.append(f"  mtf: {self.declared_keys_mtf}")
        
        # Show expanded keys (multi-output indicators expand to multiple columns)
        if self.expanded_keys_exec != self.declared_keys_exec:
            lines.append("")
            lines.append("Expanded Indicator Keys (after multi-output expansion):")
            lines.append(f"  exec: {self.expanded_keys_exec}")
            if self.expanded_keys_htf:
                lines.append(f"  htf: {self.expanded_keys_htf}")
            if self.expanded_keys_mtf:
                lines.append(f"  mtf: {self.expanded_keys_mtf}")
        if self.validation_errors:
            lines.append("")
            lines.append("Validation Errors:")
            for err in self.validation_errors:
                lines.append(f"  - {err}")
        return "\n".join(lines)


# =============================================================================
# Preflight Check (tools-layer)
# =============================================================================

def backtest_preflight_idea_card_tool(
    idea_card_id: str,
    env: DataEnv = DEFAULT_DATA_ENV,
    symbol: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    idea_cards_dir: Optional[Path] = None,
) -> ToolResult:
    """
    Run preflight check for an IdeaCard backtest.
    
    This is the Phase A gate. Validates:
    - IdeaCard loads and validates
    - env/symbol/tf are correct
    - DuckDB has sufficient coverage for effective window (with warmup)
    
    Args:
        idea_card_id: IdeaCard identifier
        env: Data environment ("live" or "demo")
        symbol: Override symbol (default: first in IdeaCard.symbol_universe)
        start: Window start (default: derive from IdeaCard or DB)
        end: Window end (default: now)
        idea_cards_dir: Override IdeaCard directory
        
    Returns:
        ToolResult with PreflightDiagnostics in data
    """
    try:
        # Validate env
        env = validate_data_env(env)
        db_path = resolve_db_path(env)
        ohlcv_table = resolve_table_name("ohlcv", env)
        
        # Load IdeaCard
        try:
            idea_card = load_idea_card(idea_card_id, base_dir=idea_cards_dir)
        except FileNotFoundError as e:
            return ToolResult(
                success=False,
                error=str(e),
                data={
                    "env": env,
                    "db_path": str(db_path),
                    "available_idea_cards": list_idea_cards(idea_cards_dir),
                },
            )
        
        # Validate IdeaCard
        validation = validate_idea_card_full(idea_card)
        
        # Resolve symbol
        if symbol is None:
            if not idea_card.symbol_universe:
                return ToolResult(
                    success=False,
                    error="IdeaCard has no symbols in symbol_universe and none provided",
                )
            symbol = idea_card.symbol_universe[0]
        
        # Validate symbol
        symbol = validate_symbol(symbol)
        try:
            validate_usdt_pair(symbol)
        except ValueError as e:
            return ToolResult(
                success=False,
                error=str(e),
            )
        
        # Validate exec_tf
        exec_tf = validate_canonical_tf(idea_card.exec_tf)
        htf = validate_canonical_tf(idea_card.htf) if idea_card.htf else None
        mtf = validate_canonical_tf(idea_card.mtf) if idea_card.mtf else None
        
        # Normalize timestamps
        if start:
            start = normalize_timestamp(start)
        if end:
            end = normalize_timestamp(end)
        else:
            end = datetime.now().replace(tzinfo=None)
        
        # Compute warmup
        warmup_req = compute_warmup_requirements(idea_card)
        warmup_bars = warmup_req.max_warmup_bars
        tf_minutes = TF_MINUTES.get(exec_tf, 15)
        warmup_span_minutes = warmup_bars * tf_minutes
        
        # Compute effective window
        if start:
            effective_start = start - timedelta(minutes=warmup_span_minutes)
        else:
            # If no start provided, we'll derive from DB
            effective_start = None
        effective_end = end
        
        # Get declared feature keys
        declared = get_declared_features_by_role(idea_card)
        declared_keys_exec = sorted(declared.get("exec", set()))
        declared_keys_htf = sorted(declared.get("htf", set()))
        declared_keys_mtf = sorted(declared.get("mtf", set()))
        
        # Compute expanded keys (multi-output indicators expand to multiple columns)
        # E.g., macd -> macd_macd, macd_signal, macd_hist
        expanded_keys_exec = []
        expanded_keys_htf = []
        expanded_keys_mtf = []
        
        for role, tf_config in idea_card.tf_configs.items():
            specs = list(tf_config.feature_specs)
            expanded = get_required_indicator_columns_from_specs(specs)
            if role == "exec":
                expanded_keys_exec = sorted(expanded)
            elif role == "htf":
                expanded_keys_htf = sorted(expanded)
            elif role == "mtf":
                expanded_keys_mtf = sorted(expanded)
        
        # Check DB coverage
        store = get_historical_store(env=env)
        
        # Get DB range for this symbol/tf
        status = store.status(symbol)
        tf_key = f"{symbol}_{exec_tf}"
        tf_status = status.get(tf_key, {})
        
        db_earliest = tf_status.get("first_timestamp")
        db_latest = tf_status.get("last_timestamp")
        db_bar_count = tf_status.get("candle_count", 0)
        
        # Check coverage
        has_sufficient_coverage = False
        coverage_issue = None
        
        if db_bar_count == 0:
            coverage_issue = f"No data found for {symbol} {exec_tf}. Run: python trade_cli.py backtest data-fix --idea-card {idea_card_id} --env {env}"
        elif effective_start and db_earliest and effective_start < db_earliest:
            coverage_issue = (
                f"Effective window starts at {effective_start.strftime('%Y-%m-%d %H:%M')} "
                f"but DB earliest is {db_earliest.strftime('%Y-%m-%d %H:%M')}. "
                f"Either sync earlier data or reduce warmup_multiplier. "
                f"Run: python trade_cli.py backtest data-fix --idea-card {idea_card_id} --env {env} --start {effective_start.strftime('%Y-%m-%d')}"
            )
        elif effective_end and db_latest and effective_end > db_latest + timedelta(hours=1):
            coverage_issue = (
                f"Window ends at {effective_end.strftime('%Y-%m-%d %H:%M')} "
                f"but DB latest is {db_latest.strftime('%Y-%m-%d %H:%M')}. "
                f"Run: python trade_cli.py backtest data-fix --idea-card {idea_card_id} --env {env} --sync-to-now"
            )
        else:
            has_sufficient_coverage = True
        
        # Build diagnostics
        diagnostics = PreflightDiagnostics(
            env=env,
            db_path=str(db_path),
            ohlcv_table=ohlcv_table,
            symbol=symbol,
            exec_tf=exec_tf,
            htf=htf,
            mtf=mtf,
            requested_start=start,
            requested_end=end,
            effective_start=effective_start,
            effective_end=effective_end,
            warmup_bars=warmup_bars,
            warmup_span_minutes=warmup_span_minutes,
            db_earliest=db_earliest,
            db_latest=db_latest,
            db_bar_count=db_bar_count,
            has_sufficient_coverage=has_sufficient_coverage,
            coverage_issue=coverage_issue,
            declared_keys_exec=declared_keys_exec,
            declared_keys_htf=declared_keys_htf,
            declared_keys_mtf=declared_keys_mtf,
            expanded_keys_exec=expanded_keys_exec,
            expanded_keys_htf=expanded_keys_htf,
            expanded_keys_mtf=expanded_keys_mtf,
            idea_card_valid=validation.is_valid,
            idea_card_hash=validation.hash,
            validation_errors=[i.message for i in validation.errors] if validation.errors else [],
        )
        
        # Log summary
        logger.info(f"Preflight check for {idea_card_id}:\n{diagnostics.format_summary()}")
        
        # Determine success
        success = validation.is_valid and has_sufficient_coverage
        
        if not success:
            error_msg = []
            if not validation.is_valid:
                error_msg.append(f"IdeaCard validation failed: {diagnostics.validation_errors}")
            if not has_sufficient_coverage:
                error_msg.append(coverage_issue or "Insufficient DB coverage")
            
            return ToolResult(
                success=False,
                error="; ".join(error_msg),
                symbol=symbol,
                data=diagnostics.to_dict(),
            )
        
        return ToolResult(
            success=True,
            message=f"Preflight OK for {idea_card_id}: {symbol} {exec_tf}, {db_bar_count:,} bars available",
            symbol=symbol,
            data=diagnostics.to_dict(),
        )
        
    except Exception as e:
        logger.error(f"Preflight check failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Preflight check error: {e}",
        )


# =============================================================================
# Run Backtest (tools-layer)
# =============================================================================

def backtest_run_idea_card_tool(
    idea_card_id: str,
    env: DataEnv = DEFAULT_DATA_ENV,
    symbol: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    smoke: bool = False,
    strict: bool = True,
    write_artifacts: bool = True,
    artifacts_dir: Optional[Path] = None,
    idea_cards_dir: Optional[Path] = None,
    initial_equity_override: Optional[float] = None,
    max_leverage_override: Optional[float] = None,
) -> ToolResult:
    """
    Run a backtest for an IdeaCard.
    
    This is the GOLDEN PATH for backtest execution.
    All validation, data loading, and execution flows through here.
    
    Capital/account config comes from IdeaCard.account section (required).
    CLI can override specific values using the override parameters.
    
    Args:
        idea_card_id: IdeaCard identifier
        env: Data environment ("live" or "demo")
        symbol: Override symbol
        start: Window start
        end: Window end
        smoke: If True, run fast smoke check (small window if not provided)
        strict: If True, use strict indicator access (default: True)
        write_artifacts: If True, write result artifacts
        artifacts_dir: Override artifacts directory
        idea_cards_dir: Override IdeaCard directory
        initial_equity_override: Override starting equity (defaults to IdeaCard.account.starting_equity_usdt)
        max_leverage_override: Override max leverage (defaults to IdeaCard.account.max_leverage)
        
    Returns:
        ToolResult with backtest results
    """
    try:
        # Run preflight first
        preflight_result = backtest_preflight_idea_card_tool(
            idea_card_id=idea_card_id,
            env=env,
            symbol=symbol,
            start=start,
            end=end,
            idea_cards_dir=idea_cards_dir,
        )
        
        if not preflight_result.success:
            return preflight_result
        
        diagnostics = preflight_result.data
        
        # Load IdeaCard
        idea_card = load_idea_card(idea_card_id, base_dir=idea_cards_dir)
        
        # Validate account config is present (required - no defaults)
        if idea_card.account is None:
            return ToolResult(
                success=False,
                error=(
                    f"IdeaCard '{idea_card_id}' is missing account section. "
                    "account.starting_equity_usdt and account.max_leverage are required."
                ),
            )
        
        # Resolve config values (IdeaCard is source of truth, CLI can override)
        resolved_starting_equity = (
            initial_equity_override 
            if initial_equity_override is not None 
            else idea_card.account.starting_equity_usdt
        )
        resolved_max_leverage = (
            max_leverage_override 
            if max_leverage_override is not None 
            else idea_card.account.max_leverage
        )
        resolved_min_trade = idea_card.account.min_trade_notional_usdt or 1.0
        
        # Resolve symbol from diagnostics
        resolved_symbol = diagnostics["symbol"]
        exec_tf = diagnostics["exec_tf"]
        
        # Print Resolved Config Summary (Phase 5.3 requirement)
        logger.info("=" * 60)
        logger.info("RESOLVED CONFIG SUMMARY")
        logger.info("=" * 60)
        logger.info(f"  symbol: {resolved_symbol}")
        logger.info(f"  tf_exec: {exec_tf}")
        if idea_card.htf:
            logger.info(f"  tf_htf: {idea_card.htf}")
        if idea_card.mtf:
            logger.info(f"  tf_mtf: {idea_card.mtf}")
        logger.info("-" * 40)
        logger.info(f"  starting_equity_usdt: {resolved_starting_equity:,.2f}")
        logger.info(f"  max_leverage: {resolved_max_leverage:.1f}x")
        logger.info(f"  min_trade_notional_usdt: {resolved_min_trade:.2f}")
        if idea_card.account.fee_model:
            logger.info(f"  taker_fee_bps: {idea_card.account.fee_model.taker_bps}")
            logger.info(f"  maker_fee_bps: {idea_card.account.fee_model.maker_bps}")
        if idea_card.account.slippage_bps:
            logger.info(f"  slippage_bps: {idea_card.account.slippage_bps}")
        logger.info("-" * 40)
        # Warmup spans
        for role in ["exec", "htf", "mtf"]:
            if role in idea_card.tf_configs:
                warmup = idea_card.get_required_warmup_bars(role)
                tf = idea_card.tf_configs[role].tf
                logger.info(f"  warmup_{role}: {warmup} bars ({tf})")
        logger.info("=" * 60)
        
        # If smoke mode and no start/end provided, use last 100 bars from DB
        db_latest = diagnostics.get("db_latest")
        db_latest_dt = None
        if db_latest:
            db_latest_dt = datetime.fromisoformat(db_latest) if isinstance(db_latest, str) else db_latest
        
        if smoke:
            if db_latest_dt:
                # Use DB latest as end for smoke (not now(), which is always ahead)
                if end is None:
                    end = db_latest_dt
                    logger.info(f"Smoke mode: using DB latest as end={end}")
                
                # Use last 100 bars for start
                if start is None:
                    tf_minutes = TF_MINUTES.get(exec_tf, 15)
                    start = db_latest_dt - timedelta(minutes=tf_minutes * 100)
                    logger.info(f"Smoke mode: using last 100 bars, start={start}")
        
        # Normalize timestamps
        if start:
            start = normalize_timestamp(start)
        if end:
            end = normalize_timestamp(end)
        else:
            end = datetime.now().replace(tzinfo=None)
        
        # =====================================================================
        # GATE: Indicator Requirements Validation
        # Validates that required indicators are declared in FeatureSpecs
        # =====================================================================
        from ..backtest.gates.indicator_requirements_gate import (
            validate_indicator_requirements,
            IndicatorGateStatus,
        )
        
        # Build available keys from declared FeatureSpecs (expanded keys)
        available_keys_by_role = {}
        for role in ["exec", "htf", "mtf"]:
            expanded_key = f"expanded_keys_{role}"
            if expanded_key in diagnostics:
                available_keys_by_role[role] = set(diagnostics[expanded_key])
            elif f"declared_keys_{role}" in diagnostics:
                # Fallback to declared keys if expanded not available
                available_keys_by_role[role] = set(diagnostics[f"declared_keys_{role}"])
        
        indicator_gate_result = validate_indicator_requirements(
            idea_card=idea_card,
            available_keys_by_role=available_keys_by_role,
        )
        
        if indicator_gate_result.failed:
            logger.error("INDICATOR REQUIREMENTS GATE FAILED")
            logger.error(indicator_gate_result.format_error())
            return ToolResult(
                success=False,
                error=indicator_gate_result.error_message,
                data={
                    "gate": "indicator_requirements",
                    "result": indicator_gate_result.to_dict(),
                    "preflight": diagnostics,
                },
            )
        
        if indicator_gate_result.status == IndicatorGateStatus.PASSED:
            logger.info("[GATE] Indicator requirements: PASSED")
        elif indicator_gate_result.status == IndicatorGateStatus.SKIPPED:
            logger.info("[GATE] Indicator requirements: SKIPPED (no required_indicators declared)")
        
        # Print indicator keys (Phase B requirement)
        logger.info(f"Declared indicator keys (exec): {diagnostics['declared_keys_exec']}")
        if diagnostics.get("declared_keys_htf"):
            logger.info(f"Declared indicator keys (htf): {diagnostics['declared_keys_htf']}")
        if diagnostics.get("declared_keys_mtf"):
            logger.info(f"Declared indicator keys (mtf): {diagnostics['declared_keys_mtf']}")
        
        # Use the existing runner infrastructure
        from ..backtest.runner import (
            RunnerConfig,
            RunnerResult,
            run_backtest_with_gates,
            create_default_engine_factory,
        )
        
        # Set default artifacts dir
        if artifacts_dir is None:
            artifacts_dir = Path("backtests")
        
        # Create data_loader from HistoricalDataStore
        store = get_historical_store(env=env)
        
        def data_loader(symbol: str, tf: str, start_dt: datetime, end_dt: datetime) -> pd.DataFrame:
            """Load OHLCV data from DuckDB."""
            df = store.get_ohlcv(symbol, tf, start=start_dt, end=end_dt)
            if df is None:
                return pd.DataFrame()
            return df
        
        # Build runner config with correct field names
        # NOTE: skip_preflight=True because CLI wrapper already ran its own preflight
        # The runner's preflight is more strict (checks HTF/MTF warmup separately)
        # For smoke tests, we trust the CLI wrapper's preflight check
        # NOTE: skip_artifact_validation=True because we skip preflight (no preflight_report.json)
        runner_config = RunnerConfig(
            idea_card_id=idea_card_id,
            idea_card=idea_card,
            window_start=start,
            window_end=end,
            base_output_dir=artifacts_dir,
            idea_cards_dir=idea_cards_dir,
            skip_preflight=True,  # CLI wrapper already validated
            skip_artifact_validation=True,  # Skip because preflight is skipped (no preflight_report.json)
            data_loader=data_loader,
        )
        
        # Run backtest with gates
        run_result = run_backtest_with_gates(
            config=runner_config,
            engine_factory=create_default_engine_factory(),
        )
        
        # Extract results
        if not run_result.success:
            return ToolResult(
                success=False,
                error=run_result.error_message or "Backtest failed",
                symbol=resolved_symbol,
                data={
                    "preflight": diagnostics,
                    "run_result": run_result.to_dict(),
                    "gate_failed": run_result.gate_failed,
                },
            )
        
        # Build result summary
        summary = run_result.summary
        trades_count = summary.trades_count if summary else 0
        
        result_data = {
            "preflight": diagnostics,
            "idea_card_id": idea_card_id,
            "symbol": resolved_symbol,
            "exec_tf": exec_tf,
            "env": env,
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
            "smoke": smoke,
            "strict": strict,
            "trades_count": trades_count,
            "run_id": run_result.run_id,
        }
        
        if summary:
            result_data["summary"] = summary.to_dict()
        
        if run_result.artifact_path:
            result_data["artifact_dir"] = str(run_result.artifact_path)
        
        return ToolResult(
            success=True,
            message=f"Backtest complete: {trades_count} trades",
            symbol=resolved_symbol,
            data=result_data,
        )
        
    except KeyError as e:
        # Indicator key error - provide helpful message
        error_msg = str(e)
        available_info = ""
        if "not declared" in error_msg.lower() or "available" in error_msg.lower():
            available_info = " Check declared_keys in preflight output."
        
        return ToolResult(
            success=False,
            error=f"Indicator key error: {error_msg}{available_info}",
            data={"preflight": preflight_result.data if preflight_result.success else None},
        )
        
    except ValueError as e:
        error_msg = str(e)
        # Check for NaN errors and provide warmup guidance
        if "nan" in error_msg.lower():
            guidance = (
                " This may be a warmup issue (not enough bars before window start) "
                "or insufficient DB coverage. Check effective_start in preflight output."
            )
            error_msg += guidance
        
        return ToolResult(
            success=False,
            error=error_msg,
            data={"preflight": preflight_result.data if preflight_result.success else None},
        )
        
    except Exception as e:
        logger.error(f"Backtest run failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Backtest error: {e}",
        )


# =============================================================================
# Indicator Key Discovery (tools-layer)
# =============================================================================

def backtest_indicators_tool(
    idea_card_id: str,
    data_env: DataEnv = DEFAULT_DATA_ENV,
    symbol: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    idea_cards_dir: Optional[Path] = None,
    compute_values: bool = False,
) -> ToolResult:
    """
    Discover and print indicator keys for an IdeaCard.
    
    This command replaces pytest-based indicator key validation.
    Run this to see exactly what indicator keys will be computed
    so you can fix FeatureSpec/IdeaCard declarations.
    
    Args:
        idea_card_id: IdeaCard identifier
        data_env: Data environment ("live" or "demo")
        symbol: Override symbol
        start: Window start (for computing actual values)
        end: Window end
        idea_cards_dir: Override IdeaCard directory
        compute_values: If True, actually compute indicators and show first non-NaN index
        
    Returns:
        ToolResult with indicator key discovery results
    """
    try:
        # Validate env
        data_env = validate_data_env(data_env)
        db_path = resolve_db_path(data_env)
        ohlcv_table = resolve_table_name("ohlcv", data_env)
        
        # Load IdeaCard
        try:
            idea_card = load_idea_card(idea_card_id, base_dir=idea_cards_dir)
        except FileNotFoundError as e:
            return ToolResult(
                success=False,
                error=str(e),
                data={"available_idea_cards": list_idea_cards(idea_cards_dir)},
            )
        
        # Validate IdeaCard
        validation = validate_idea_card_full(idea_card)
        if not validation.is_valid:
            return ToolResult(
                success=False,
                error=f"IdeaCard validation failed: {[i.message for i in validation.errors]}",
            )
        
        # Resolve symbol
        if symbol is None:
            if not idea_card.symbol_universe:
                return ToolResult(
                    success=False,
                    error="IdeaCard has no symbols and none provided",
                )
            symbol = idea_card.symbol_universe[0]
        
        symbol = validate_symbol(symbol)
        
        # Get all feature specs by role
        feature_specs_by_role = {}
        declared_keys_by_role = {}
        expanded_keys_by_role = {}
        
        for role, tf_config in idea_card.tf_configs.items():
            specs = list(tf_config.feature_specs)
            feature_specs_by_role[role] = specs
            
            # Get declared keys (output_key from each spec)
            declared_keys_by_role[role] = sorted([s.output_key for s in specs])
            
            # Get expanded keys (including multi-output suffixes)
            expanded_keys_by_role[role] = sorted(get_required_indicator_columns_from_specs(specs))
        
        # Build result
        result_data = {
            "idea_card_id": idea_card_id,
            "data_env": data_env,
            "db_path": str(db_path),
            "symbol": symbol,
            "exec_tf": idea_card.exec_tf,
            "htf": idea_card.htf,
            "mtf": idea_card.mtf,
            "declared_keys_by_role": declared_keys_by_role,
            "expanded_keys_by_role": expanded_keys_by_role,
            "total_declared_keys": sum(len(v) for v in declared_keys_by_role.values()),
            "total_expanded_keys": sum(len(v) for v in expanded_keys_by_role.values()),
        }
        
        # If compute_values, actually load data and compute indicators
        if compute_values and start and end:
            from ..backtest.indicators import apply_feature_spec_indicators, find_first_valid_bar
            
            store = get_historical_store(env=data_env)
            
            computed_info = {}
            for role, specs in feature_specs_by_role.items():
                if not specs:
                    continue
                    
                tf = idea_card.tf_configs[role].tf
                
                # Normalize timestamps
                start_norm = normalize_timestamp(start)
                end_norm = normalize_timestamp(end) if end else datetime.now().replace(tzinfo=None)
                
                # Load data
                df = store.get_ohlcv(symbol, tf, start_norm, end_norm)
                
                if df is None or df.empty:
                    computed_info[role] = {"error": f"No data for {symbol} {tf}"}
                    continue
                
                # Apply indicators
                df = apply_feature_spec_indicators(df, specs)
                
                # Find first valid bar
                expanded_cols = get_required_indicator_columns_from_specs(specs)
                first_valid = find_first_valid_bar(df, expanded_cols)
                
                # Get actual computed columns
                actual_cols = [c for c in df.columns if c not in ['timestamp', 'open', 'high', 'low', 'close', 'volume']]
                
                computed_info[role] = {
                    "tf": tf,
                    "data_rows": len(df),
                    "first_valid_bar": first_valid,
                    "computed_columns": sorted(actual_cols),
                    "all_indicators_valid": first_valid >= 0,
                }
            
            result_data["computed_info"] = computed_info
        
        # Log output
        logger.info(f"Indicator key discovery for {idea_card_id}:")
        for role in ["exec", "htf", "mtf"]:
            if role in declared_keys_by_role:
                declared = declared_keys_by_role[role]
                expanded = expanded_keys_by_role[role]
                logger.info(f"  {role} ({idea_card.tf_configs.get(role, {}).tf if role in idea_card.tf_configs else 'N/A'}):")
                logger.info(f"    declared: {declared}")
                logger.info(f"    expanded: {expanded}")
        
        return ToolResult(
            success=True,
            message=f"Found {result_data['total_expanded_keys']} indicator keys across {len(feature_specs_by_role)} TF roles",
            symbol=symbol,
            data=result_data,
        )
        
    except Exception as e:
        logger.error(f"Indicator discovery failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Indicator discovery error: {e}",
        )


# =============================================================================
# Data Fix (tools-layer dispatch to existing tools)
# =============================================================================

def backtest_data_fix_tool(
    idea_card_id: str,
    env: DataEnv = DEFAULT_DATA_ENV,
    symbol: Optional[str] = None,
    start: Optional[datetime] = None,
    sync_to_now: bool = False,
    fill_gaps: bool = True,
    heal: bool = False,
    idea_cards_dir: Optional[Path] = None,
) -> ToolResult:
    """
    Fix data for an IdeaCard backtest by calling existing data tools.
    
    No new DB logic - dispatches to existing sync/fill/heal tools.
    
    Args:
        idea_card_id: IdeaCard identifier
        env: Data environment
        symbol: Override symbol
        start: Sync from this date (default: IdeaCard warmup requirements)
        sync_to_now: If True, sync data to current time
        fill_gaps: If True, fill gaps after sync
        heal: If True, run full heal after sync
        idea_cards_dir: Override IdeaCard directory
        
    Returns:
        ToolResult with data fix summary
    """
    from .data_tools import (
        sync_range_tool,
        sync_to_now_and_fill_gaps_tool,
        fill_gaps_tool,
        heal_data_tool,
    )
    
    try:
        # Validate env
        env = validate_data_env(env)
        db_path = resolve_db_path(env)
        
        # Load IdeaCard to get TFs
        idea_card = load_idea_card(idea_card_id, base_dir=idea_cards_dir)
        
        # Resolve symbol
        if symbol is None:
            if not idea_card.symbol_universe:
                return ToolResult(
                    success=False,
                    error="IdeaCard has no symbols and none provided",
                )
            symbol = idea_card.symbol_universe[0]
        
        symbol = validate_symbol(symbol)
        
        # Get all TFs from IdeaCard
        tfs = set()
        for role, tf_config in idea_card.tf_configs.items():
            tfs.add(tf_config.tf)
        tfs = sorted(tfs)
        
        results = []
        
        logger.info(f"Data fix for {idea_card_id}: env={env}, db={db_path}, symbol={symbol}, tfs={tfs}")
        
        # Sync range if start provided
        if start and not sync_to_now:
            start = normalize_timestamp(start)
            end = datetime.now().replace(tzinfo=None)
            
            result = sync_range_tool(
                symbols=[symbol],
                start=start,
                end=end,
                timeframes=tfs,
                env=env,
            )
            results.append(("sync_range", result))
        
        # Sync to now + fill gaps
        if sync_to_now:
            result = sync_to_now_and_fill_gaps_tool(
                symbols=[symbol],
                timeframes=tfs,
                env=env,
            )
            results.append(("sync_to_now_and_fill_gaps", result))
        
        # Fill gaps
        if fill_gaps and not sync_to_now:
            for tf in tfs:
                result = fill_gaps_tool(
                    symbol=symbol,
                    timeframe=tf,
                    env=env,
                )
                results.append((f"fill_gaps_{tf}", result))
        
        # Heal
        if heal:
            result = heal_data_tool(
                symbol=symbol,
                env=env,
            )
            results.append(("heal", result))
        
        # Summarize
        all_success = all(r[1].success for r in results)
        summary = {
            "env": env,
            "db_path": str(db_path),
            "symbol": symbol,
            "tfs": tfs,
            "operations": [
                {"name": name, "success": result.success, "message": result.message or result.error}
                for name, result in results
            ],
        }
        
        if all_success:
            return ToolResult(
                success=True,
                message=f"Data fix complete for {symbol}: {len(results)} operations",
                symbol=symbol,
                data=summary,
            )
        else:
            failed = [r[0] for r in results if not r[1].success]
            return ToolResult(
                success=False,
                error=f"Some operations failed: {failed}",
                symbol=symbol,
                data=summary,
            )
            
    except Exception as e:
        logger.error(f"Data fix failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Data fix error: {e}",
        )


# =============================================================================
# List IdeaCards (tools-layer)
# =============================================================================

def backtest_list_idea_cards_tool(
    idea_cards_dir: Optional[Path] = None,
) -> ToolResult:
    """
    List available IdeaCards.
    
    Args:
        idea_cards_dir: Override IdeaCard directory
        
    Returns:
        ToolResult with list of IdeaCard IDs
    """
    try:
        cards = list_idea_cards(base_dir=idea_cards_dir)
        
        return ToolResult(
            success=True,
            message=f"Found {len(cards)} IdeaCards",
            data={
                "idea_cards": cards,
                "directory": str(idea_cards_dir) if idea_cards_dir else "configs/idea_cards/",
            },
        )
        
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to list IdeaCards: {e}",
        )


# =============================================================================
# IdeaCard Normalization (build-time validation)
# =============================================================================

def backtest_idea_card_normalize_tool(
    idea_card_id: str,
    idea_cards_dir: Optional[Path] = None,
    write_in_place: bool = False,
) -> ToolResult:
    """
    Normalize and validate an IdeaCard YAML at build time.
    
    This command validates:
    - All indicator_types are supported
    - All params are accepted by each indicator
    - All signal_rules/risk_model references use expanded keys (not base keys)
    
    If validation passes and write_in_place=True, writes the normalized YAML
    with auto-generated required_indicators.
    
    Agent Rule:
        Agents may only generate IdeaCards through this command and must
        refuse to write YAML if normalization fails.
    
    Args:
        idea_card_id: IdeaCard identifier
        idea_cards_dir: Override IdeaCard directory
        write_in_place: If True, write normalized YAML back to file
        
    Returns:
        ToolResult with validation results
    """
    import yaml
    from ..backtest.idea_card import IDEA_CARDS_DIR
    from ..backtest.idea_card_yaml_builder import (
        normalize_idea_card_yaml,
        format_validation_errors,
    )
    
    try:
        # Resolve path
        search_dir = idea_cards_dir or IDEA_CARDS_DIR
        yaml_path = None
        
        for ext in (".yml", ".yaml"):
            path = search_dir / f"{idea_card_id}{ext}"
            if path.exists():
                yaml_path = path
                break
        
        if yaml_path is None:
            cards = list_idea_cards(base_dir=idea_cards_dir)
            return ToolResult(
                success=False,
                error=f"IdeaCard '{idea_card_id}' not found in {search_dir}",
                data={"available_idea_cards": cards},
            )
        
        # Load raw YAML
        with open(yaml_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        
        if not raw:
            return ToolResult(
                success=False,
                error=f"Empty or invalid YAML in {yaml_path}",
            )
        
        # Normalize and validate
        normalized, result = normalize_idea_card_yaml(raw, auto_generate_required=True)
        
        if not result.is_valid:
            error_details = format_validation_errors(result.errors)
            return ToolResult(
                success=False,
                error=f"IdeaCard validation failed with {len(result.errors)} error(s)",
                data={
                    "idea_card_id": idea_card_id,
                    "yaml_path": str(yaml_path),
                    "errors": [e.to_dict() for e in result.errors],
                    "error_details": error_details,
                },
            )
        
        # If write_in_place, write back the normalized YAML
        if write_in_place:
            with open(yaml_path, "w", encoding="utf-8") as f:
                yaml.dump(normalized, f, sort_keys=False, default_flow_style=False)
            
            return ToolResult(
                success=True,
                message=f"IdeaCard '{idea_card_id}' normalized and written to {yaml_path}",
                data={
                    "idea_card_id": idea_card_id,
                    "yaml_path": str(yaml_path),
                    "normalized": True,
                    "written": True,
                },
            )
        
        # Dry-run: just return validation success
        return ToolResult(
            success=True,
            message=f"IdeaCard '{idea_card_id}' passed validation (dry-run, not written)",
            data={
                "idea_card_id": idea_card_id,
                "yaml_path": str(yaml_path),
                "normalized": True,
                "written": False,
                "warnings": result.warnings,
            },
        )
        
    except Exception as e:
        logger.error(f"IdeaCard normalization failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Normalization error: {e}",
        )


# =============================================================================
# Audit Toolkit (indicator registry consistency check)
# =============================================================================

def backtest_audit_toolkit_tool() -> ToolResult:
    """
    Audit the indicator toolkit for internal consistency.
    
    Validates:
    - All indicators in IndicatorRegistry are actually callable in pandas_ta
    - Multi-output indicators have correct output_keys defined
    - MULTI_OUTPUT_KEYS in feature_spec.py matches registry
    
    Returns:
        ToolResult with audit results
    """
    try:
        import pandas_ta as ta
        from ..backtest.indicator_registry import (
            get_registry,
            SUPPORTED_INDICATORS,
        )
        from ..backtest.features.feature_spec import MULTI_OUTPUT_KEYS, IndicatorType
        
        registry = get_registry()
        issues: List[Dict[str, Any]] = []
        
        # Check each supported indicator exists in pandas_ta
        for name in registry.list_indicators():
            func = getattr(ta, name, None)
            if func is None or not callable(func):
                issues.append({
                    "type": "MISSING_IN_PANDAS_TA",
                    "indicator": name,
                    "message": f"Indicator '{name}' is in SUPPORTED_INDICATORS but not found in pandas_ta",
                })
        
        # Check multi-output indicators have output_keys
        for name, spec in SUPPORTED_INDICATORS.items():
            if spec.get("multi_output", False):
                output_keys = spec.get("output_keys", ())
                if not output_keys:
                    issues.append({
                        "type": "MISSING_OUTPUT_KEYS",
                        "indicator": name,
                        "message": f"Multi-output indicator '{name}' has no output_keys defined",
                    })
                if not spec.get("primary_output"):
                    issues.append({
                        "type": "MISSING_PRIMARY_OUTPUT",
                        "indicator": name,
                        "message": f"Multi-output indicator '{name}' has no primary_output defined",
                    })
        
        # Check MULTI_OUTPUT_KEYS consistency
        for ind_type, keys in MULTI_OUTPUT_KEYS.items():
            name = ind_type.value
            if name in SUPPORTED_INDICATORS:
                registry_keys = tuple(SUPPORTED_INDICATORS[name].get("output_keys", ()))
                if registry_keys and registry_keys != keys:
                    issues.append({
                        "type": "OUTPUT_KEYS_MISMATCH",
                        "indicator": name,
                        "message": (
                            f"Mismatch between MULTI_OUTPUT_KEYS and SUPPORTED_INDICATORS: "
                            f"MULTI_OUTPUT_KEYS has {keys}, registry has {registry_keys}"
                        ),
                    })
        
        if issues:
            return ToolResult(
                success=False,
                error=f"Toolkit audit found {len(issues)} issue(s)",
                data={
                    "issues": issues,
                    "supported_indicators": registry.list_indicators(),
                },
            )
        
        return ToolResult(
            success=True,
            message="Toolkit audit passed: all indicators consistent",
            data={
                "supported_indicators": registry.list_indicators(),
                "multi_output_count": sum(
                    1 for s in SUPPORTED_INDICATORS.values() if s.get("multi_output")
                ),
                "single_output_count": sum(
                    1 for s in SUPPORTED_INDICATORS.values() if not s.get("multi_output")
                ),
            },
        )
        
    except Exception as e:
        logger.error(f"Toolkit audit failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Audit error: {e}",
        )
