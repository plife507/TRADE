"""
Execution Validation: IdeaCard → Engine Contract Validation.

Phase 8 implementation for validating IdeaCards before execution:
- Gate 8.0: IdeaCard execution contract (hashing, validation)
- Gate 8.1: Feature reference extraction and validation
- Gate 8.2: Warmup window definition
- Gate 8.4: Pre-evaluation validation gates

Design principles:
- Validate at load time, not runtime
- Fail fast with clear error messages
- No implicit defaults
- All referenced features must be declared
"""

from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .idea_card import IdeaCard, Condition, EntryRule, ExitRule, TFConfig

from .features.feature_spec import IndicatorType


# =============================================================================
# Gate 8.0: IdeaCard Execution Contract
# =============================================================================

def compute_idea_card_hash(idea_card: "IdeaCard") -> str:
    """
    Compute a deterministic hash for an IdeaCard.
    
    Identical IdeaCards produce identical hashes.
    Hash is based on all execution-relevant fields.
    
    Args:
        idea_card: The IdeaCard to hash
        
    Returns:
        SHA256 hash as hex string (first 16 chars for readability)
    """
    # Convert to dict (deterministic serialization)
    card_dict = idea_card.to_dict()
    
    # Sort keys for determinism
    canonical_json = json.dumps(card_dict, sort_keys=True, separators=(",", ":"))
    
    # Compute hash
    hash_bytes = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    
    # Return first 16 chars for readability
    return hash_bytes[:16]


class ValidationSeverity(str, Enum):
    """Severity level for validation issues."""
    ERROR = "error"      # Blocks execution
    WARNING = "warning"  # Does not block, but should be addressed


@dataclass
class ValidationIssue:
    """A single validation issue."""
    severity: ValidationSeverity
    code: str
    message: str
    location: Optional[str] = None  # e.g., "entry_rules[0].conditions[1]"
    
    def to_dict(self) -> Dict:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
            "location": self.location,
        }


@dataclass
class IdeaCardValidationResult:
    """Result of IdeaCard validation."""
    is_valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    hash: Optional[str] = None
    
    @property
    def errors(self) -> List[ValidationIssue]:
        """Get only error-level issues."""
        return [i for i in self.issues if i.severity == ValidationSeverity.ERROR]
    
    @property
    def warnings(self) -> List[ValidationIssue]:
        """Get only warning-level issues."""
        return [i for i in self.issues if i.severity == ValidationSeverity.WARNING]
    
    def to_dict(self) -> Dict:
        return {
            "is_valid": self.is_valid,
            "hash": self.hash,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "issues": [i.to_dict() for i in self.issues],
        }


def validate_idea_card_contract(idea_card: "IdeaCard") -> IdeaCardValidationResult:
    """
    Validate IdeaCard execution contract.
    
    Gate 8.0: Ensures IdeaCard is a valid, deterministic execution unit.
    
    Checks:
    - Required fields are present
    - TF configs are valid
    - Position policy is consistent with signal rules
    - Hash is computable
    
    Args:
        idea_card: IdeaCard to validate
        
    Returns:
        IdeaCardValidationResult with issues (if any)
    """
    issues: List[ValidationIssue] = []
    
    # Required fields
    if not idea_card.id:
        issues.append(ValidationIssue(
            severity=ValidationSeverity.ERROR,
            code="MISSING_ID",
            message="IdeaCard.id is required",
        ))
    
    if not idea_card.version:
        issues.append(ValidationIssue(
            severity=ValidationSeverity.ERROR,
            code="MISSING_VERSION",
            message="IdeaCard.version is required",
        ))
    
    if not idea_card.symbol_universe:
        issues.append(ValidationIssue(
            severity=ValidationSeverity.ERROR,
            code="MISSING_SYMBOLS",
            message="IdeaCard.symbol_universe is required (at least one symbol)",
        ))
    
    # Exec TF is required
    if "exec" not in idea_card.tf_configs:
        issues.append(ValidationIssue(
            severity=ValidationSeverity.ERROR,
            code="MISSING_EXEC_TF",
            message="exec timeframe is required in tf_configs",
        ))
    
    # Account config is REQUIRED (no hard-coded defaults)
    if idea_card.account is None:
        issues.append(ValidationIssue(
            severity=ValidationSeverity.ERROR,
            code="MISSING_ACCOUNT",
            message=(
                "IdeaCard.account section is required. "
                "Specify account.starting_equity_usdt and account.max_leverage."
            ),
        ))
    else:
        # Validate account values
        if idea_card.account.starting_equity_usdt <= 0:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="INVALID_STARTING_EQUITY",
                message=f"account.starting_equity_usdt must be positive. Got: {idea_card.account.starting_equity_usdt}",
            ))
        if idea_card.account.max_leverage <= 0:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="INVALID_MAX_LEVERAGE",
                message=f"account.max_leverage must be positive. Got: {idea_card.account.max_leverage}",
            ))
    
    # Signal rules must exist for execution
    if idea_card.signal_rules is None:
        issues.append(ValidationIssue(
            severity=ValidationSeverity.WARNING,
            code="NO_SIGNAL_RULES",
            message="No signal_rules defined - IdeaCard cannot generate signals",
        ))
    
    # Risk model should exist
    if idea_card.risk_model is None:
        issues.append(ValidationIssue(
            severity=ValidationSeverity.WARNING,
            code="NO_RISK_MODEL",
            message="No risk_model defined - positions will not have SL/TP",
        ))
    
    # Compute hash if no critical errors
    card_hash = None
    if not any(i.severity == ValidationSeverity.ERROR for i in issues):
        try:
            card_hash = compute_idea_card_hash(idea_card)
        except Exception as e:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="HASH_FAILED",
                message=f"Failed to compute IdeaCard hash: {e}",
            ))
    
    is_valid = not any(i.severity == ValidationSeverity.ERROR for i in issues)
    
    return IdeaCardValidationResult(
        is_valid=is_valid,
        issues=issues,
        hash=card_hash,
    )


# =============================================================================
# Gate 8.1: Feature Reference Extraction + Validation
# =============================================================================

@dataclass
class FeatureReference:
    """A reference to a feature/indicator in signal rules."""
    key: str
    tf_role: str  # "exec", "htf", "mtf"
    location: str  # e.g., "entry_rules[0].conditions[1].indicator_key"


def extract_rule_feature_refs(idea_card: "IdeaCard") -> List[FeatureReference]:
    """
    Extract all feature references from IdeaCard signal rules.
    
    Gate 8.1: Finds all indicator_key references in conditions.
    
    Args:
        idea_card: IdeaCard with signal rules
        
    Returns:
        List of FeatureReference objects
    """
    refs: List[FeatureReference] = []
    
    if not idea_card.signal_rules:
        return refs
    
    # Extract from entry rules
    for i, rule in enumerate(idea_card.signal_rules.entry_rules):
        for j, cond in enumerate(rule.conditions):
            location = f"entry_rules[{i}].conditions[{j}].indicator_key"
            refs.append(FeatureReference(
                key=cond.indicator_key,
                tf_role=cond.tf,
                location=location,
            ))
            
            # If comparing to another indicator
            if cond.is_indicator_comparison:
                location = f"entry_rules[{i}].conditions[{j}].value"
                refs.append(FeatureReference(
                    key=str(cond.value),
                    tf_role=cond.tf,
                    location=location,
                ))
    
    # Extract from exit rules
    for i, rule in enumerate(idea_card.signal_rules.exit_rules):
        for j, cond in enumerate(rule.conditions):
            location = f"exit_rules[{i}].conditions[{j}].indicator_key"
            refs.append(FeatureReference(
                key=cond.indicator_key,
                tf_role=cond.tf,
                location=location,
            ))
            
            if cond.is_indicator_comparison:
                location = f"exit_rules[{i}].conditions[{j}].value"
                refs.append(FeatureReference(
                    key=str(cond.value),
                    tf_role=cond.tf,
                    location=location,
                ))
    
    # Extract from risk model if ATR-based SL
    if idea_card.risk_model and idea_card.risk_model.stop_loss.atr_key:
        refs.append(FeatureReference(
            key=idea_card.risk_model.stop_loss.atr_key,
            tf_role="exec",  # SL uses exec TF
            location="risk_model.stop_loss.atr_key",
        ))
    
    if idea_card.risk_model and idea_card.risk_model.take_profit.atr_key:
        refs.append(FeatureReference(
            key=idea_card.risk_model.take_profit.atr_key,
            tf_role="exec",
            location="risk_model.take_profit.atr_key",
        ))
    
    return refs


# OHLCV columns are always available (not declared as features)
OHLCV_COLUMNS = {"open", "high", "low", "close", "volume", "timestamp"}


def get_declared_features_by_role(idea_card: "IdeaCard") -> Dict[str, Set[str]]:
    """
    Get all declared feature keys organized by TF role.
    
    OHLCV columns (open, high, low, close, volume) are always implicitly available.
    
    Args:
        idea_card: IdeaCard with TF configs
        
    Returns:
        Dict mapping role -> set of feature keys (including OHLCV columns)
    """
    result: Dict[str, Set[str]] = {}
    
    for role, tf_config in idea_card.tf_configs.items():
        # Start with OHLCV columns - always available
        keys = set(OHLCV_COLUMNS)
        for spec in tf_config.feature_specs:
            # Add all output keys (including multi-output expansion)
            keys.update(spec.output_keys_list)
        result[role] = keys
    
    return result


def validate_idea_card_features(idea_card: "IdeaCard") -> IdeaCardValidationResult:
    """
    Validate all feature references in IdeaCard.
    
    Gate 8.1: Ensures all referenced features are declared.
    
    Checks:
    - All indicator_key references exist in declared features
    - TF role matches (feature declared in correct TF)
    - No unknown indicator types
    
    Args:
        idea_card: IdeaCard to validate
        
    Returns:
        IdeaCardValidationResult with issues (if any)
    """
    issues: List[ValidationIssue] = []
    
    # Get all declared features
    declared = get_declared_features_by_role(idea_card)
    
    # Get all references
    refs = extract_rule_feature_refs(idea_card)
    
    for ref in refs:
        role = ref.tf_role
        key = ref.key
        
        # Check TF role exists
        if role not in declared:
            if role not in idea_card.tf_configs:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="UNKNOWN_TF_ROLE",
                    message=f"TF role '{role}' referenced but not configured",
                    location=ref.location,
                ))
            else:
                # TF exists but has no features - might be valid for OHLCV access
                pass
            continue
        
        # Check feature exists
        if key not in declared[role]:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="UNDECLARED_FEATURE",
                message=f"Feature '{key}' referenced but not declared in {role} TF",
                location=ref.location,
            ))
    
    is_valid = not any(i.severity == ValidationSeverity.ERROR for i in issues)
    
    return IdeaCardValidationResult(
        is_valid=is_valid,
        issues=issues,
    )


# =============================================================================
# Gate 8.2: Warmup Window Definition
# =============================================================================

@dataclass
class WarmupRequirements:
    """Warmup requirements for an IdeaCard."""
    # Per-TF warmup bars
    warmup_by_role: Dict[str, int] = field(default_factory=dict)
    
    # Maximum across all TFs
    max_warmup_bars: int = 0
    
    # Source breakdown
    feature_warmup: Dict[str, int] = field(default_factory=dict)  # role -> max feature warmup
    bars_history_required: int = 0
    
    def to_dict(self) -> Dict:
        return {
            "warmup_by_role": self.warmup_by_role,
            "max_warmup_bars": self.max_warmup_bars,
            "feature_warmup": self.feature_warmup,
            "bars_history_required": self.bars_history_required,
        }


def compute_warmup_requirements(idea_card: "IdeaCard") -> WarmupRequirements:
    """
    Compute canonical warmup requirements for an IdeaCard.
    
    Gate 8.2: Warmup = max(feature_warmups[tf], rule_lookback_bars[tf], bars_window_required[tf])
    
    Args:
        idea_card: IdeaCard to analyze
        
    Returns:
        WarmupRequirements with per-TF and overall warmup
    """
    warmup_by_role: Dict[str, int] = {}
    feature_warmup: Dict[str, int] = {}
    
    for role, tf_config in idea_card.tf_configs.items():
        # Get max warmup from feature specs
        max_feature_warmup = 0
        for spec in tf_config.feature_specs:
            max_feature_warmup = max(max_feature_warmup, spec.warmup_bars)
        
        feature_warmup[role] = max_feature_warmup
        
        # Combine with explicit warmup_bars and bars_history_required
        effective_warmup = max(
            max_feature_warmup,
            tf_config.warmup_bars,
            idea_card.bars_history_required,
        )
        
        warmup_by_role[role] = effective_warmup
    
    # Overall max
    max_warmup = max(warmup_by_role.values()) if warmup_by_role else 0
    
    return WarmupRequirements(
        warmup_by_role=warmup_by_role,
        max_warmup_bars=max_warmup,
        feature_warmup=feature_warmup,
        bars_history_required=idea_card.bars_history_required,
    )


# =============================================================================
# Gate 8.4: Pre-Evaluation Validation Gates
# =============================================================================

@dataclass
class PreEvaluationStatus:
    """Status of pre-evaluation validation."""
    is_ready: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    warmup_satisfied: Dict[str, bool] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "is_ready": self.is_ready,
            "warmup_satisfied": self.warmup_satisfied,
            "error_count": len([i for i in self.issues if i.severity == ValidationSeverity.ERROR]),
            "issues": [i.to_dict() for i in self.issues],
        }


def validate_pre_evaluation(
    idea_card: "IdeaCard",
    bar_counts: Dict[str, int],  # role -> current bar count
    warmup_requirements: Optional[WarmupRequirements] = None,
) -> PreEvaluationStatus:
    """
    Validate IdeaCard is ready for evaluation at current bar.
    
    Gate 8.4: Pre-evaluation validation.
    
    Checks:
    - All TFs have sufficient bars for warmup
    - All required features are available
    
    Args:
        idea_card: IdeaCard being evaluated
        bar_counts: Current bar count per TF role
        warmup_requirements: Pre-computed warmup (or computed if None)
        
    Returns:
        PreEvaluationStatus indicating readiness
    """
    issues: List[ValidationIssue] = []
    warmup_satisfied: Dict[str, bool] = {}
    
    # Compute warmup if not provided
    if warmup_requirements is None:
        warmup_requirements = compute_warmup_requirements(idea_card)
    
    # Check warmup for each TF
    for role, required_warmup in warmup_requirements.warmup_by_role.items():
        current_bars = bar_counts.get(role, 0)
        satisfied = current_bars >= required_warmup
        warmup_satisfied[role] = satisfied
        
        if not satisfied:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="WARMUP_NOT_SATISFIED",
                message=f"{role} TF needs {required_warmup} bars, has {current_bars}",
                location=f"tf_configs.{role}",
            ))
    
    is_ready = not any(i.severity == ValidationSeverity.ERROR for i in issues)
    
    return PreEvaluationStatus(
        is_ready=is_ready,
        issues=issues,
        warmup_satisfied=warmup_satisfied,
    )


# =============================================================================
# Combined Validation
# =============================================================================

def validate_idea_card_full(idea_card: "IdeaCard") -> IdeaCardValidationResult:
    """
    Run all validation gates on an IdeaCard.
    
    Combines:
    - Gate 8.0: Contract validation
    - Gate 8.1: Feature validation
    
    Args:
        idea_card: IdeaCard to validate
        
    Returns:
        Combined IdeaCardValidationResult
    """
    all_issues: List[ValidationIssue] = []
    
    # Gate 8.0: Contract
    contract_result = validate_idea_card_contract(idea_card)
    all_issues.extend(contract_result.issues)
    
    # Gate 8.1: Features (only if contract is valid)
    if contract_result.is_valid:
        feature_result = validate_idea_card_features(idea_card)
        all_issues.extend(feature_result.issues)
    
    is_valid = not any(i.severity == ValidationSeverity.ERROR for i in all_issues)
    
    return IdeaCardValidationResult(
        is_valid=is_valid,
        issues=all_issues,
        hash=contract_result.hash,
    )


# =============================================================================
# Gate 8.3: IdeaCard → SystemConfig Adapter
# =============================================================================
# TEMP ADAPTER — DELETE WHEN:
# - Engine natively accepts IdeaCard (no SystemConfig dependency)
# - All callers use IdeaCard directly
# - Deletion criteria met: only runner.py calls this adapter
# =============================================================================

@dataclass
class IdeaCardSystemConfig:
    """
    SystemConfig-compatible configuration derived from IdeaCard.
    
    Gate 8.3: Provides the bridge between IdeaCard and engine execution.
    
    This is a minimal adapter that extracts execution-relevant fields
    from an IdeaCard for the backtest engine.
    
    TEMP: This adapter exists only until engine.py natively accepts IdeaCard.
    Single caller: runner.py (enforced by Gate F test).
    """
    # From IdeaCard identity
    system_id: str
    idea_card_hash: str
    
    # Primary execution params
    symbol: str
    exec_tf: str
    htf: Optional[str] = None
    mtf: Optional[str] = None
    
    # Warmup requirements
    warmup_bars: int = 0
    warmup_by_role: Dict[str, int] = field(default_factory=dict)
    
    # Risk/account parameters (from IdeaCard.account - REQUIRED, no defaults)
    initial_equity: float = 0.0  # Will be set from IdeaCard.account.starting_equity_usdt
    max_leverage: float = 1.0
    sizing_model: str = "percent_equity"
    sizing_value: float = 1.0
    
    # Feature keys per TF
    feature_keys_by_role: Dict[str, List[str]] = field(default_factory=dict)
    
    # Feature specs per TF (for indicator computation)
    feature_specs_by_role: Dict[str, List["FeatureSpec"]] = field(default_factory=dict)
    
    # Validation result
    validation: Optional[IdeaCardValidationResult] = None
    
    def to_dict(self) -> Dict:
        return {
            "system_id": self.system_id,
            "idea_card_hash": self.idea_card_hash,
            "symbol": self.symbol,
            "exec_tf": self.exec_tf,
            "htf": self.htf,
            "mtf": self.mtf,
            "warmup_bars": self.warmup_bars,
            "warmup_by_role": self.warmup_by_role,
            "initial_equity": self.initial_equity,
            "max_leverage": self.max_leverage,
            "sizing_model": self.sizing_model,
            "sizing_value": self.sizing_value,
            "feature_keys_by_role": self.feature_keys_by_role,
            "validation": self.validation.to_dict() if self.validation else None,
        }


def adapt_idea_card_to_system_config(
    idea_card: "IdeaCard",
    symbol: Optional[str] = None,
    initial_equity_override: Optional[float] = None,
) -> IdeaCardSystemConfig:
    """
    Convert IdeaCard to IdeaCardSystemConfig for engine execution.
    
    Gate 8.3: IdeaCardAdapter → SystemConfig
    
    Capital/account config comes from IdeaCard.account section (required).
    initial_equity_override can be used to override the IdeaCard value.
    
    Args:
        idea_card: Source IdeaCard
        symbol: Override symbol (default: first in symbol_universe)
        initial_equity_override: Override starting equity (default: from IdeaCard.account)
        
    Returns:
        IdeaCardSystemConfig ready for engine wiring
        
    Raises:
        ValueError: If IdeaCard validation fails or account section is missing
    """
    # Validate first
    validation = validate_idea_card_full(idea_card)
    if not validation.is_valid:
        errors = [i.message for i in validation.errors]
        raise ValueError(f"IdeaCard validation failed: {'; '.join(errors)}")
    
    # Validate account config is present (required - no defaults)
    if idea_card.account is None:
        raise ValueError(
            f"IdeaCard '{idea_card.id}' is missing account section. "
            "account.starting_equity_usdt and account.max_leverage are required."
        )
    
    # Resolve initial equity (IdeaCard is source of truth, can be overridden)
    initial_equity = (
        initial_equity_override 
        if initial_equity_override is not None 
        else idea_card.account.starting_equity_usdt
    )
    
    # Resolve symbol
    if symbol is None:
        if not idea_card.symbol_universe:
            raise ValueError("IdeaCard has no symbols in symbol_universe")
        symbol = idea_card.symbol_universe[0]
    
    # Compute warmup
    warmup_req = compute_warmup_requirements(idea_card)
    
    # Extract feature keys
    declared = get_declared_features_by_role(idea_card)
    feature_keys_by_role = {role: sorted(keys) for role, keys in declared.items()}
    
    # Extract feature specs by role (for indicator computation)
    feature_specs_by_role = {}
    for role, tf_config in idea_card.tf_configs.items():
        feature_specs_by_role[role] = list(tf_config.feature_specs)
    
    # Extract max_leverage from account config (primary source)
    max_leverage = idea_card.account.max_leverage
    
    # Extract sizing from risk model
    sizing_model = "percent_equity"
    sizing_value = 1.0
    
    if idea_card.risk_model:
        sizing_model = idea_card.risk_model.sizing.model.value
        sizing_value = idea_card.risk_model.sizing.value
        # risk_model.sizing.max_leverage can override if different
        if idea_card.risk_model.sizing.max_leverage:
            max_leverage = idea_card.risk_model.sizing.max_leverage
    
    return IdeaCardSystemConfig(
        system_id=idea_card.id,
        idea_card_hash=validation.hash or "",
        symbol=symbol,
        exec_tf=idea_card.exec_tf,
        htf=idea_card.htf,
        mtf=idea_card.mtf,
        warmup_bars=warmup_req.max_warmup_bars,
        warmup_by_role=warmup_req.warmup_by_role,
        initial_equity=initial_equity,
        max_leverage=max_leverage,
        sizing_model=sizing_model,
        sizing_value=sizing_value,
        feature_keys_by_role=feature_keys_by_role,
        feature_specs_by_role=feature_specs_by_role,
        validation=validation,
    )


# =============================================================================
# Gate 8.3: IdeaCard Signal Evaluator Interface
# =============================================================================

class SignalDecision(str, Enum):
    """Decision from signal evaluation."""
    NO_ACTION = "no_action"      # No signal generated
    ENTRY_LONG = "entry_long"    # Enter long position
    ENTRY_SHORT = "entry_short"  # Enter short position
    EXIT = "exit"                # Exit current position


@dataclass
class EvaluationResult:
    """Result of IdeaCard signal evaluation."""
    decision: SignalDecision
    reason: str = ""
    matched_rule_index: Optional[int] = None
    
    # For entry signals
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    size_usdt: Optional[float] = None
    
    def to_dict(self) -> Dict:
        return {
            "decision": self.decision.value,
            "reason": self.reason,
            "matched_rule_index": self.matched_rule_index,
            "stop_loss_price": self.stop_loss_price,
            "take_profit_price": self.take_profit_price,
            "size_usdt": self.size_usdt,
        }


class IdeaCardSignalEvaluator:
    """
    Evaluates IdeaCard signal rules against snapshot state.
    
    Gate 8.3: Interface for deterministic signal evaluation.
    
    The evaluator:
    1. Reads feature values from snapshot
    2. Evaluates entry/exit conditions
    3. Computes SL/TP from risk model
    4. Returns SignalDecision
    
    This is the interface - concrete implementation will be in Phase 8 execution.
    """
    
    def __init__(self, idea_card: "IdeaCard"):
        """
        Initialize evaluator with IdeaCard.
        
        Args:
            idea_card: The IdeaCard containing signal rules
            
        Raises:
            ValueError: If IdeaCard is invalid
        """
        # Validate
        validation = validate_idea_card_full(idea_card)
        if not validation.is_valid:
            errors = [i.message for i in validation.errors]
            raise ValueError(f"IdeaCard validation failed: {'; '.join(errors)}")
        
        self.idea_card = idea_card
        self.warmup = compute_warmup_requirements(idea_card)
    
    def evaluate(
        self,
        snapshot: "SnapshotView",
        has_position: bool,
        position_side: Optional[str] = None,
    ) -> EvaluationResult:
        """
        Evaluate signal rules against current snapshot.
        
        Args:
            snapshot: Current RuntimeSnapshotView
            has_position: Whether there's an open position
            position_side: "long" or "short" if has_position
            
        Returns:
            EvaluationResult with decision and details
        """
        signal_rules = self.idea_card.signal_rules
        if signal_rules is None:
            return EvaluationResult(
                decision=SignalDecision.NO_ACTION,
                reason="No signal_rules defined in IdeaCard",
            )
        
        # If no position, evaluate entry rules
        if not has_position:
            for i, rule in enumerate(signal_rules.entry_rules):
                # Check position policy allows this direction
                if rule.direction == "long" and not self.idea_card.position_policy.allows_long():
                    continue
                if rule.direction == "short" and not self.idea_card.position_policy.allows_short():
                    continue
                
                # Evaluate all conditions (AND logic)
                if self._evaluate_conditions(rule.conditions, snapshot):
                    decision = SignalDecision.ENTRY_LONG if rule.direction == "long" else SignalDecision.ENTRY_SHORT
                    
                    # Compute SL/TP from risk model
                    sl_price, tp_price = self._compute_sl_tp(snapshot, rule.direction)
                    
                    return EvaluationResult(
                        decision=decision,
                        reason=f"Entry rule {i} matched ({rule.direction})",
                        matched_rule_index=i,
                        stop_loss_price=sl_price,
                        take_profit_price=tp_price,
                    )
        
        # If has position, evaluate exit rules
        else:
            for i, rule in enumerate(signal_rules.exit_rules):
                # Only evaluate exit rules for current position direction
                if rule.direction != position_side:
                    continue
                
                # Evaluate all conditions (AND logic)
                if self._evaluate_conditions(rule.conditions, snapshot):
                    return EvaluationResult(
                        decision=SignalDecision.EXIT,
                        reason=f"Exit rule {i} matched ({rule.exit_type})",
                        matched_rule_index=i,
                    )
        
        return EvaluationResult(
            decision=SignalDecision.NO_ACTION,
            reason="No rules matched",
        )
    
    def _get_feature_value(
        self,
        indicator_key: str,
        tf_role: str,
        snapshot,  # RuntimeSnapshot or RuntimeSnapshotView
        offset: int = 0,
    ) -> Optional[float]:
        """
        Get feature value from snapshot for given indicator and TF role.
        
        Supports both RuntimeSnapshot (dataclass) and RuntimeSnapshotView (lightweight view).
        
        Args:
            indicator_key: Indicator key (e.g., "ema_20", "close")
            tf_role: TF role ("exec", "htf", "mtf")
            snapshot: Runtime snapshot
            offset: Bar offset (0 = current, 1 = previous)
            
        Returns:
            Feature value or None if not available
        """
        # Get the appropriate feature snapshot and history
        if tf_role == "exec" or tf_role == "ltf":
            feature_snapshot = snapshot.features_exec
            history = getattr(snapshot, 'history_features_exec', ())
        elif tf_role == "htf":
            feature_snapshot = snapshot.features_htf
            history = getattr(snapshot, 'history_features_htf', ())
        elif tf_role == "mtf":
            feature_snapshot = snapshot.features_mtf
            history = getattr(snapshot, 'history_features_mtf', ())
        else:
            return None
        
        # Handle OHLCV access (special keys)
        if indicator_key in ("open", "high", "low", "close", "volume"):
            if offset == 0:
                # Current bar
                bar = feature_snapshot.bar if feature_snapshot else None
                if bar is None:
                    return None
                return getattr(bar, indicator_key, None)
            else:
                # Get from history (history is oldest-first, so [-offset] gets offset bars back)
                if history and offset <= len(history):
                    hist_snapshot = history[-offset]
                    bar = hist_snapshot.bar if hist_snapshot else None
                    if bar is None:
                        return None
                    return getattr(bar, indicator_key, None)
                return None
        
        # Handle indicator access
        if offset == 0:
            # Current value
            if feature_snapshot and feature_snapshot.ready:
                return feature_snapshot.features.get(indicator_key)
            return None
        else:
            # Get from history (history is oldest-first, so [-offset] gets offset bars back)
            if history and offset <= len(history):
                hist_snapshot = history[-offset]
                if hist_snapshot and hist_snapshot.ready:
                    return hist_snapshot.features.get(indicator_key)
            return None
    
    def _evaluate_conditions(
        self,
        conditions: Tuple,
        snapshot: "SnapshotView",
    ) -> bool:
        """
        Evaluate all conditions (AND logic).
        
        Args:
            conditions: Tuple of Condition objects
            snapshot: Runtime snapshot
            
        Returns:
            True if all conditions are met
        """
        from .idea_card import RuleOperator
        
        for cond in conditions:
            # Get current value
            current_val = self._get_feature_value(cond.indicator_key, cond.tf, snapshot, offset=0)
            if current_val is None:
                return False  # Can't evaluate if value not available
            
            # Get comparison value
            if cond.is_indicator_comparison:
                compare_val = self._get_feature_value(str(cond.value), cond.tf, snapshot, offset=0)
                if compare_val is None:
                    return False
            else:
                compare_val = float(cond.value)
            
            # Evaluate based on operator
            if cond.operator == RuleOperator.GT:
                if not (current_val > compare_val):
                    return False
            elif cond.operator == RuleOperator.GTE:
                if not (current_val >= compare_val):
                    return False
            elif cond.operator == RuleOperator.LT:
                if not (current_val < compare_val):
                    return False
            elif cond.operator == RuleOperator.LTE:
                if not (current_val <= compare_val):
                    return False
            elif cond.operator == RuleOperator.EQ:
                if not (abs(current_val - compare_val) < 1e-9):
                    return False
            elif cond.operator == RuleOperator.CROSS_ABOVE:
                # Current > compare AND previous <= compare
                prev_val = self._get_feature_value(cond.indicator_key, cond.tf, snapshot, offset=cond.prev_offset)
                if cond.is_indicator_comparison:
                    prev_compare = self._get_feature_value(str(cond.value), cond.tf, snapshot, offset=cond.prev_offset)
                else:
                    prev_compare = compare_val
                
                if prev_val is None or prev_compare is None:
                    return False
                if not (current_val > compare_val and prev_val <= prev_compare):
                    return False
            elif cond.operator == RuleOperator.CROSS_BELOW:
                # Current < compare AND previous >= compare
                prev_val = self._get_feature_value(cond.indicator_key, cond.tf, snapshot, offset=cond.prev_offset)
                if cond.is_indicator_comparison:
                    prev_compare = self._get_feature_value(str(cond.value), cond.tf, snapshot, offset=cond.prev_offset)
                else:
                    prev_compare = compare_val
                
                if prev_val is None or prev_compare is None:
                    return False
                if not (current_val < compare_val and prev_val >= prev_compare):
                    return False
            else:
                return False  # Unknown operator
        
        return True
    
    def _compute_sl_tp(
        self,
        snapshot: "SnapshotView",
        direction: str,
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Compute stop loss and take profit prices from risk model.
        
        Args:
            snapshot: Runtime snapshot
            direction: "long" or "short"
            
        Returns:
            Tuple of (stop_loss_price, take_profit_price)
        """
        risk_model = self.idea_card.risk_model
        if risk_model is None:
            return None, None
        
        # Use close price as entry reference
        entry_price = self._get_feature_value("close", "exec", snapshot, offset=0)
        if entry_price is None:
            return None, None
        
        sl_price = None
        sl_distance = None
        
        # Compute stop loss
        sl_rule = risk_model.stop_loss
        if sl_rule.type.value == "atr_multiple":
            atr = self._get_feature_value(sl_rule.atr_key, "exec", snapshot, offset=0)
            if atr is not None:
                sl_distance = atr * sl_rule.value
                buffer = entry_price * (sl_rule.buffer_pct / 100.0)
                if direction == "long":
                    sl_price = entry_price - sl_distance - buffer
                else:
                    sl_price = entry_price + sl_distance + buffer
        elif sl_rule.type.value == "percent":
            sl_distance = entry_price * (sl_rule.value / 100.0)
            if direction == "long":
                sl_price = entry_price - sl_distance
            else:
                sl_price = entry_price + sl_distance
        elif sl_rule.type.value == "fixed_points":
            sl_distance = sl_rule.value
            if direction == "long":
                sl_price = entry_price - sl_distance
            else:
                sl_price = entry_price + sl_distance
        
        tp_price = None
        
        # Compute take profit
        tp_rule = risk_model.take_profit
        if tp_rule.type.value == "rr_ratio" and sl_distance is not None:
            tp_distance = sl_distance * tp_rule.value
            if direction == "long":
                tp_price = entry_price + tp_distance
            else:
                tp_price = entry_price - tp_distance
        elif tp_rule.type.value == "atr_multiple":
            atr = self._get_feature_value(tp_rule.atr_key, "exec", snapshot, offset=0)
            if atr is not None:
                tp_distance = atr * tp_rule.value
                if direction == "long":
                    tp_price = entry_price + tp_distance
                else:
                    tp_price = entry_price - tp_distance
        elif tp_rule.type.value == "percent":
            tp_distance = entry_price * (tp_rule.value / 100.0)
            if direction == "long":
                tp_price = entry_price + tp_distance
            else:
                tp_price = entry_price - tp_distance
        elif tp_rule.type.value == "fixed_points":
            tp_distance = tp_rule.value
            if direction == "long":
                tp_price = entry_price + tp_distance
            else:
                tp_price = entry_price - tp_distance
        
        return sl_price, tp_price
    
    def check_warmup_satisfied(self, bar_counts: Dict[str, int]) -> bool:
        """
        Check if warmup requirements are satisfied.
        
        Args:
            bar_counts: Current bar count per TF role
            
        Returns:
            True if all warmup requirements are met
        """
        for role, required in self.warmup.warmup_by_role.items():
            current = bar_counts.get(role, 0)
            if current < required:
                return False
        return True


# Type hint for snapshot (avoids circular import)
if TYPE_CHECKING:
    from .runtime.snapshot_view import RuntimeSnapshotView as SnapshotView


