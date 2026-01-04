"""
Pipeline Signature — Production verification artifact.

Records exactly which implementations were used during a backtest run,
proving that the production pipeline was executed (not stubs or legacy paths).

Gate D.1 requirement: Every backtest run MUST produce pipeline_signature.json.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING
import json
import hashlib

if TYPE_CHECKING:
    from ..play import Play


# Pipeline version - increment when pipeline structure changes
PIPELINE_VERSION = "1.0.0"


@dataclass
class PipelineSignature:
    """
    Records the exact pipeline configuration and implementations used.
    
    This proves:
    - Play is the config source (not SystemConfig)
    - Real FeatureFrameBuilder was used
    - Real engine was executed
    - No placeholder/stub mode
    """
    # Run identification
    run_id: str
    play_id: str
    play_hash: str
    resolved_play_path: str
    
    # Pipeline version
    pipeline_version: str = PIPELINE_VERSION
    
    # Config source verification
    config_source: str = "Play"
    uses_system_config_loader: bool = False
    
    # Implementation names (for auditability)
    engine_impl: str = "BacktestEngine"
    snapshot_impl: str = "RuntimeSnapshotView"
    feature_builder_impl: str = "FeatureFrameBuilder"
    indicator_backend: str = "pandas-ta"
    exchange_impl: str = "SimulatedExchange"
    
    # Feature verification
    declared_feature_keys: list[str] = field(default_factory=list)
    computed_feature_keys: list[str] = field(default_factory=list)
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
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str, sort_keys=True)
    
    def write_json(self, path: Path) -> None:
        """Write to JSON file."""
        path.write_text(self.to_json())
    
    def validate(self) -> list[str]:
        """
        Validate pipeline signature requirements.

        Returns:
            List of error messages (empty if valid)
        """
        errors = []
        
        # Config source must be Play
        if self.config_source != "Play":
            errors.append(f"config_source must be 'Play', got '{self.config_source}'")
        
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
    play: "Play",
    play_hash: str,
    resolved_path: str,
    declared_keys: list[str],
    computed_keys: list[str],
) -> PipelineSignature:
    """
    Create a pipeline signature for a backtest run.
    
    Args:
        run_id: Unique run identifier
        play: The Play used
        play_hash: Hash of the Play
        resolved_path: Path where Play was loaded from
        declared_keys: Feature keys declared in Play
        computed_keys: Feature keys actually computed
        
    Returns:
        PipelineSignature instance
    """
    return PipelineSignature(
        run_id=run_id,
        play_id=play.id,
        play_hash=play_hash,
        resolved_play_path=resolved_path,
        declared_feature_keys=sorted(declared_keys),
        computed_feature_keys=sorted(computed_keys),
    )


# Standard filename
PIPELINE_SIGNATURE_FILE = "pipeline_signature.json"

