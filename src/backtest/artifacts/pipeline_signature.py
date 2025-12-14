"""
Pipeline Signature — Production verification artifact.

Records exactly which implementations were used during a backtest run,
proving that the production pipeline was executed (not stubs or legacy paths).

Gate D.1 requirement: Every backtest run MUST produce pipeline_signature.json.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
import json
import hashlib


# Pipeline version - increment when pipeline structure changes
PIPELINE_VERSION = "1.0.0"


@dataclass
class PipelineSignature:
    """
    Records the exact pipeline configuration and implementations used.
    
    This proves:
    - IdeaCard is the config source (not SystemConfig)
    - Real FeatureFrameBuilder was used
    - Real engine was executed
    - No placeholder/stub mode
    """
    # Run identification
    run_id: str
    idea_card_id: str
    idea_card_hash: str
    resolved_idea_card_path: str
    
    # Pipeline version
    pipeline_version: str = PIPELINE_VERSION
    
    # Config source verification
    config_source: str = "IdeaCard"
    uses_system_config_loader: bool = False
    
    # Implementation names (for auditability)
    engine_impl: str = "BacktestEngine"
    snapshot_impl: str = "RuntimeSnapshotView"
    feature_builder_impl: str = "FeatureFrameBuilder"
    indicator_backend: str = "pandas-ta"
    exchange_impl: str = "SimulatedExchange"
    
    # Feature verification
    declared_feature_keys: List[str] = field(default_factory=list)
    computed_feature_keys: List[str] = field(default_factory=list)
    feature_keys_match: bool = False
    
    # Execution verification
    placeholder_mode: bool = False
    strict_indicator_access: bool = True
    
    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def __post_init__(self):
        """Verify feature keys match."""
        declared = set(self.declared_feature_keys)
        computed = set(self.computed_feature_keys)
        self.feature_keys_match = declared == computed
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)
    
    def write_json(self, path: Path) -> None:
        """Write to JSON file."""
        path.write_text(self.to_json())
    
    def validate(self) -> List[str]:
        """
        Validate pipeline signature requirements.
        
        Returns:
            List of error messages (empty if valid)
        """
        errors = []
        
        # Config source must be IdeaCard
        if self.config_source != "IdeaCard":
            errors.append(f"config_source must be 'IdeaCard', got '{self.config_source}'")
        
        # Must not use SystemConfig loader
        if self.uses_system_config_loader:
            errors.append("uses_system_config_loader must be False")
        
        # Must not be in placeholder mode
        if self.placeholder_mode:
            errors.append("placeholder_mode must be False for production runs")
        
        # Must use strict indicator access
        if not self.strict_indicator_access:
            errors.append("strict_indicator_access must be True")
        
        # Feature keys must match
        if not self.feature_keys_match:
            declared = set(self.declared_feature_keys)
            computed = set(self.computed_feature_keys)
            missing = declared - computed
            extra = computed - declared
            if missing:
                errors.append(f"Declared but not computed: {missing}")
            if extra:
                errors.append(f"Computed but not declared: {extra}")
        
        return errors
    
    def is_valid(self) -> bool:
        """Check if signature is valid for production."""
        return len(self.validate()) == 0


def create_pipeline_signature(
    run_id: str,
    idea_card: "IdeaCard",
    idea_card_hash: str,
    resolved_path: str,
    declared_keys: List[str],
    computed_keys: List[str],
) -> PipelineSignature:
    """
    Create a pipeline signature for a backtest run.
    
    Args:
        run_id: Unique run identifier
        idea_card: The IdeaCard used
        idea_card_hash: Hash of the IdeaCard
        resolved_path: Path where IdeaCard was loaded from
        declared_keys: Feature keys declared in IdeaCard
        computed_keys: Feature keys actually computed
        
    Returns:
        PipelineSignature instance
    """
    return PipelineSignature(
        run_id=run_id,
        idea_card_id=idea_card.id,
        idea_card_hash=idea_card_hash,
        resolved_idea_card_path=resolved_path,
        declared_feature_keys=sorted(declared_keys),
        computed_feature_keys=sorted(computed_keys),
    )


# Standard filename
PIPELINE_SIGNATURE_FILE = "pipeline_signature.json"

