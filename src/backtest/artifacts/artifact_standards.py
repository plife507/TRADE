"""
Artifact Naming + Export Standards.

Defines the canonical folder/file naming conventions for backtest artifacts.
All backtest runs MUST produce artifacts in this format.

Folder structure (hash-based, deterministic):
    backtests/
    └── {category}/                    # _validation or strategies
        └── {play_id}/
            └── {symbol}/
                └── {12-char-input-hash}/
                    ├── run_manifest.json      # Full hash + all inputs
                    ├── result.json            # Final metrics
                    ├── trades.parquet         # Trade log
                    ├── equity.parquet         # Equity curve
                    ├── pipeline_signature.json
                    └── logs/                  # Run logs

Categories:
- _validation: Engine validation and test runs (non-promotable)
- strategies: Research/production backtests (promotable)

Hash determinism:
- Same inputs = same folder = same results
- Full hash stored in run_manifest.json
- Folder name uses 12-char short hash
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json


class VersionMismatchError(Exception):
    """
    Raised when loading artifacts with incompatible schema versions.

    Provides actionable error messages with:
    - Expected vs actual version
    - Migration guidance if available
    """
    def __init__(self, expected: str, actual: str, artifact_type: str = "manifest"):
        self.expected = expected
        self.actual = actual
        self.artifact_type = artifact_type
        super().__init__(
            f"VERSION_MISMATCH: {artifact_type} version '{actual}' is incompatible with "
            f"current version '{expected}'. "
            f"Re-run the backtest to regenerate artifacts with the current schema."
        )


# Current manifest schema version - increment when RunManifest structure changes
MANIFEST_SCHEMA_VERSION = "1.0.0"


def _utcnow() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


# =============================================================================
# Standard File Names
# =============================================================================

STANDARD_FILES = {
    # Core manifest (REQUIRED for every run)
    "run_manifest": "run_manifest.json",
    # JSON artifacts
    "result": "result.json",
    "preflight": "preflight_report.json",
    "pipeline_signature": "pipeline_signature.json",
    "events": "events.jsonl",  # Event log (JSON Lines format)
    "returns": "returns.json",  # Phase 4: Time-based analytics
    # Phase 3.2: Parquet is primary format for tabular artifacts
    "trades": "trades.parquet",
    "equity": "equity.parquet",
    "account_curve": "account_curve.parquet",
    # Logs directory
    "logs_dir": "logs",
}

# Required files that MUST exist after a successful run (Phase 3.2: Parquet)
REQUIRED_FILES = {
    "result.json", 
    "trades.parquet",  # Phase 3.2: Changed from .csv
    "equity.parquet",  # Phase 3.2: Changed from .csv
    "pipeline_signature.json",  # Gate D.1 requirement
}

# Optional files (may not exist depending on run configuration)
OPTIONAL_FILES = {
    "events.jsonl",
    "account_curve.parquet",
    "preflight_report.json",  # Optional when CLI runs its own preflight
    "returns.json",  # Phase 4: Time-based analytics (may not exist for short backtests)
}


# =============================================================================
# Required Columns in Artifact Files
# =============================================================================

REQUIRED_TRADES_COLUMNS = {
    "entry_time",
    "exit_time",
    "side",
    "entry_price",
    "exit_price",
    "entry_size_usdt",
    "net_pnl",
    "stop_loss",
    "take_profit",
    "exit_reason",
}

REQUIRED_EQUITY_COLUMNS = {
    "timestamp",
    "equity",
    "ts_ms",  # Phase 6: epoch-ms for smoke test assertions
}

REQUIRED_RESULT_FIELDS = {
    "play_id",
    "symbol",
    "tf_exec",
    "window_start",
    "window_end",
    "run_id",
    "trades_count",
    "net_pnl_usdt",
}


# =============================================================================
# Artifact Path Builder
# =============================================================================

# =============================================================================
# Run Categories & Overwrite Semantics
# =============================================================================
#
# CATEGORY SEMANTICS:
#
# _validation/
#   - Purpose: Engine plumbing, math verification, audit tests
#   - Overwrite: ALLOWED (deterministic overwrite)
#   - Same input hash → same folder → previous artifacts replaced
#   - Promotable: NO (never eligible for production)
#
# strategies/
#   - Purpose: Research/production strategy backtests
#   - Overwrite: NOT ALLOWED (append-only)
#   - Same input hash → same folder → NEW attempt subfolder created
#   - Structure: {hash}/attempts/{timestamp}/
#   - Promotable: YES (eligible for promotion pipeline)
#
# =============================================================================

RUN_CATEGORIES: set[str] = {"_validation", "strategies"}

# Category-specific behavior
CATEGORY_OVERWRITE_ALLOWED = {
    "_validation": True,   # Deterministic overwrite OK
    "strategies": False,   # Append-only, preserve history
}

CATEGORY_PROMOTABLE = {
    "_validation": False,  # Never promotable
    "strategies": True,    # Can be promoted to production
}


@dataclass
class ArtifactPathConfig:
    """
    Configuration for building artifact paths.
    
    FOLDER STRUCTURE:
        {base_dir}/{category}/{play_id}/{universe_id}/{run_hash}/
        
        For strategies (append-only):
        {base_dir}/strategies/{play_id}/{universe_id}/{run_hash}/attempts/{timestamp}/
    
    CATEGORIES:
    - _validation: Engine validation and test runs
      - Overwrite: ALLOWED (same hash = same folder, replaces artifacts)
      - Promotable: NO
      
    - strategies: Research/production backtests
      - Overwrite: NOT ALLOWED (append-only, creates attempts subfolder)
      - Promotable: YES
    
    UNIVERSE_ID:
    - Single symbol: symbol name (e.g., "BTCUSDT")
    - Multiple symbols: hash of sorted list (e.g., "uni_a1b2c3d4")
    
    This resolves symbol redundancy between folder paths, Play IDs, and manifests.
    
    RUN_HASH:
    - Default: 8-char short hash
    - Collision recovery: 12-char extended hash
    
    Window dates and timeframe are stored in run_manifest.json, not folder names.
    """
    base_dir: Path = field(default_factory=lambda: Path("backtests"))
    category: str = "_validation"  # "_validation" or "strategies"
    play_id: str = ""
    universe_id: str = ""  # Symbol or uni_<hash> for multi-symbol
    tf_exec: str = ""  # Stored in manifest, not in path
    window_start: datetime | None = None  # Stored in manifest
    window_end: datetime | None = None    # Stored in manifest
    run_id: str = ""  # 8-char (or 12-char) input hash
    play_hash: str = ""  # Required for hash computation
    short_hash_length: int = 12  # Match DEFAULT_SHORT_HASH_LENGTH in hashes.py
    attempt_id: str | None = None  # Timestamp for strategies category
    
    def __post_init__(self):
        """Generate run_id (input hash) if not provided."""
        # Validate category
        if self.category not in RUN_CATEGORIES:
            raise ValueError(f"Invalid category: {self.category}. Must be one of {RUN_CATEGORIES}")
        
        # Generate hash-based run_id if not provided
        if not self.run_id and self.play_hash and self.window_start and self.window_end:
            from .hashes import compute_input_hash
            self.run_id = compute_input_hash(
                play_hash=self.play_hash,
                window_start=self.window_start.strftime("%Y-%m-%d"),
                window_end=self.window_end.strftime("%Y-%m-%d"),
                short_hash_length=self.short_hash_length,
            )
        
        # For strategies category, generate attempt_id if not provided
        if self.category == "strategies" and not self.attempt_id:
            self.attempt_id = _utcnow().strftime("%Y%m%d_%H%M%S")
    
    @property
    def allows_overwrite(self) -> bool:
        """Check if this category allows deterministic overwrite."""
        return CATEGORY_OVERWRITE_ALLOWED.get(self.category, False)
    
    @property
    def is_promotable(self) -> bool:
        """Check if runs in this category are eligible for promotion."""
        return CATEGORY_PROMOTABLE.get(self.category, False)
    
    @property
    def window_str(self) -> str:
        """Get window string for metadata (not used in path)."""
        if self.window_start and self.window_end:
            start_str = self.window_start.strftime("%Y-%m-%d")
            end_str = self.window_end.strftime("%Y-%m-%d")
            return f"{start_str} to {end_str}"
        return "unknown"
    
    @property
    def run_folder(self) -> Path:
        """
        Get the full path to the run folder.
        
        _validation structure:
            {base_dir}/_validation/{play_id}/{universe_id}/{run_id}/
            
        strategies structure (append-only):
            {base_dir}/strategies/{play_id}/{universe_id}/{run_id}/attempts/{attempt_id}/
        
        Example: 
            backtests/_validation/test__ema_atr/BTCUSDT/a1b2c3d4/
            backtests/strategies/momentum_v3/uni_b2c3d4e5/x9y8z7w6/attempts/20251217_113000/
        """
        base_path = (
            self.base_dir
            / self.category
            / self.play_id
            / self.universe_id
            / self.run_id
        )
        
        # Strategies use append-only subfolder structure
        if self.category == "strategies" and self.attempt_id:
            return base_path / "attempts" / self.attempt_id
        
        return base_path
    
    def get_file_path(self, file_key: str) -> Path:
        """Get path to a standard file."""
        if file_key not in STANDARD_FILES:
            raise ValueError(f"Unknown file key: {file_key}. Valid keys: {list(STANDARD_FILES.keys())}")
        return self.run_folder / STANDARD_FILES[file_key]
    
    def create_folder(self) -> Path:
        """Create the run folder and return its path."""
        self.run_folder.mkdir(parents=True, exist_ok=True)
        return self.run_folder
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "base_dir": str(self.base_dir),
            "category": self.category,
            "play_id": self.play_id,
            "universe_id": self.universe_id,
            "tf_exec": self.tf_exec,
            "window_start": self.window_start.isoformat() if self.window_start else None,
            "window_end": self.window_end.isoformat() if self.window_end else None,
            "run_id": self.run_id,
            "short_hash_length": self.short_hash_length,
            "attempt_id": self.attempt_id,
            "allows_overwrite": self.allows_overwrite,
            "is_promotable": self.is_promotable,
            "run_folder": str(self.run_folder),
        }


# =============================================================================
# Run Manifest (Content-Addressed Run Identity)
# =============================================================================
#
# MANIFEST RULES:
# 1. Every run folder MUST contain a run_manifest.json
# 2. Manifest stores FULL hash (64 chars) and short hash (8 or 12 chars)
# 3. Short hash derivation method is explicit (not assumed)
# 4. On load: verify folder name == short_hash AND full_hash.startswith(short_hash)
# 5. On collision: fail hard, require extended short hash (12 chars)
#
# DISCOVERY RULES:
# 1. Tooling MUST NOT assume sequential or numeric run IDs
# 2. All discovery MUST be hash-driven or manifest-driven
# 3. Folder listing finds hash folders, then validates via manifest
#
# =============================================================================

@dataclass
class RunManifest:
    """
    Mandatory manifest for every backtest run.
    
    GUARANTEES:
    - Full input hash for determinism verification
    - All hashed inputs explicitly listed (no implicit defaults)
    - Hash derivation method documented for safety
    - Version info for reproducibility
    - Timestamp for audit trail
    
    VERIFICATION (on load):
    - folder_name == short_hash
    - full_hash.startswith(short_hash)
    - short_hash_length matches actual short_hash length
    """
    # =========================================================================
    # REQUIRED FIELDS (no defaults) - must come first in dataclass
    # =========================================================================
    
    # Hash Identity
    full_hash: str            # Full 64-char SHA256 hash of all inputs
    short_hash: str           # First N chars (folder name)
    short_hash_length: int    # 8 (default) or 12 (collision recovery)
    
    # Strategy Config
    play_id: str
    play_hash: str
    
    # Symbol Universe
    symbols: list[str]        # Canonical: sorted, uppercase

    # Timeframes
    tf_exec: str              # Execution timeframe ({value}{unit} format)
    tf_ctx: list[str]         # All context timeframes (sorted)
    
    # Window
    window_start: str         # YYYY-MM-DD
    window_end: str           # YYYY-MM-DD
    
    # =========================================================================
    # OPTIONAL FIELDS (with defaults) - must come after required fields
    # =========================================================================
    
    # Hash algorithm
    hash_algorithm: str = "sha256"
    
    # Symbol universe ID
    universe_id: str = ""     # Single symbol or uni_<hash>
    
    # Execution Model Versions
    fee_model_version: str = "1.0.0"
    simulator_version: str = "1.0.0"
    engine_version: str = "1.0.0"
    fill_policy_version: str = "1.0.0"
    
    # Data Provenance
    data_source_id: str = "duckdb_live"   # e.g., "duckdb_live", "duckdb_demo", vendor
    data_version: str | None = None     # Snapshot/version reference if available
    candle_policy: str = "closed_only"     # "closed_only" (no partial candles)

    # Randomness
    seed: int | None = None
    
    # Category & Overwrite Semantics
    category: str = "_validation"     # "_validation" or "strategies"
    is_promotable: bool = False       # _validation = never promotable
    allows_overwrite: bool = True     # _validation = overwrite, strategies = append
    attempt_id: str | None = None  # For strategies: timestamp of this attempt

    # Warmup/Delay (audit-only - SOURCE OF TRUTH is SystemConfig, not manifest)
    # These fields are for reproducibility audit trail only
    # RENAMED: computed_warmup_by_role → computed_lookback_bars_by_role (breaking change)
    computed_lookback_bars_by_role: dict[str, int] | None = None  # lookback (warmup) from Preflight
    computed_delay_bars_by_role: dict[str, int] | None = None  # delay from Preflight
    warmup_tool_calls: list[dict[str, Any]] | None = None  # Tool calls made during auto-backfill

    # Phase 6: Engine-truth evaluation start (epoch-ms)
    eval_start_ts_ms: int | None = None  # simulation_start_ts from engine result
    equity_timestamp_column: str = "ts_ms"  # Column name for equity timestamp (standardized)
    
    # Audit Trail
    created_at_utc: str = ""          # ISO8601 timestamp

    # Schema version for compatibility checking
    schema_version: str = MANIFEST_SCHEMA_VERSION
    
    def __post_init__(self):
        """Set defaults and enforce invariants."""
        if not self.created_at_utc:
            self.created_at_utc = _utcnow().isoformat()
        
        # Enforce category-specific semantics
        if self.category == "_validation":
            self.is_promotable = False
            self.allows_overwrite = True
        elif self.category == "strategies":
            self.is_promotable = True
            self.allows_overwrite = False
        
        # Compute universe_id if not provided
        if not self.universe_id and self.symbols:
            from .hashes import compute_universe_id
            self.universe_id = compute_universe_id(self.symbols)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        result = {
            # Hash identity
            "full_hash": self.full_hash,
            "short_hash": self.short_hash,
            "short_hash_length": self.short_hash_length,
            "hash_algorithm": self.hash_algorithm,
            
            # Strategy config
            "play_id": self.play_id,
            "play_hash": self.play_hash,
            
            # Symbol universe
            "symbols": self.symbols,
            "universe_id": self.universe_id,
            
            # Timeframes
            "tf_exec": self.tf_exec,
            "tf_ctx": self.tf_ctx,
            
            # Window
            "window_start": self.window_start,
            "window_end": self.window_end,
            
            # Execution model versions
            "fee_model_version": self.fee_model_version,
            "simulator_version": self.simulator_version,
            "engine_version": self.engine_version,
            "fill_policy_version": self.fill_policy_version,
            
            # Data provenance
            "data_source_id": self.data_source_id,
            "data_version": self.data_version,
            "candle_policy": self.candle_policy,
            
            # Randomness
            "seed": self.seed,
            
            # Category & semantics
            "category": self.category,
            "is_promotable": self.is_promotable,
            "allows_overwrite": self.allows_overwrite,
            "attempt_id": self.attempt_id,
            
            # Audit trail
            "created_at_utc": self.created_at_utc,

            # Schema version
            "schema_version": self.schema_version,
        }
        
        # Warmup/delay audit trail (optional - only present if Preflight ran)
        # RENAMED: computed_warmup_by_role → computed_lookback_bars_by_role (breaking change)
        if self.computed_lookback_bars_by_role is not None:
            result["computed_lookback_bars_by_role"] = self.computed_lookback_bars_by_role
        if self.computed_delay_bars_by_role is not None:
            result["computed_delay_bars_by_role"] = self.computed_delay_bars_by_role
        if self.warmup_tool_calls is not None:
            result["warmup_tool_calls"] = self.warmup_tool_calls
        
        # Phase 6: Engine-truth evaluation start
        if self.eval_start_ts_ms is not None:
            result["eval_start_ts_ms"] = self.eval_start_ts_ms
        result["equity_timestamp_column"] = self.equity_timestamp_column
        
        return result
    
    def write_json(self, path: Path) -> None:
        """Write manifest to JSON file."""
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True))
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunManifest":
        """
        Load manifest from dict with version compatibility check.

        Raises:
            VersionMismatchError: If schema_version is incompatible with current version.
        """
        # Version compatibility check (fail-loud)
        stored_version = data.get("schema_version", "0.0.0")  # Pre-versioned manifests default to 0.0.0
        if stored_version != MANIFEST_SCHEMA_VERSION:
            # Check major version compatibility (major.minor.patch)
            stored_major = stored_version.split(".")[0] if stored_version else "0"
            current_major = MANIFEST_SCHEMA_VERSION.split(".")[0]
            if stored_major != current_major:
                raise VersionMismatchError(
                    expected=MANIFEST_SCHEMA_VERSION,
                    actual=stored_version,
                    artifact_type="RunManifest",
                )

        return cls(
            # Hash identity
            full_hash=data["full_hash"],
            short_hash=data["short_hash"],
            short_hash_length=data.get("short_hash_length", 12),
            hash_algorithm=data.get("hash_algorithm", "sha256"),
            
            # Strategy config
            play_id=data["play_id"],
            play_hash=data["play_hash"],
            
            # Symbol universe
            symbols=data["symbols"],
            universe_id=data.get("universe_id", ""),
            
            # Timeframes
            tf_exec=data["tf_exec"],
            tf_ctx=data["tf_ctx"],
            
            # Window
            window_start=data["window_start"],
            window_end=data["window_end"],
            
            # Execution model versions
            fee_model_version=data.get("fee_model_version", "1.0.0"),
            simulator_version=data.get("simulator_version", "1.0.0"),
            engine_version=data.get("engine_version", "1.0.0"),
            fill_policy_version=data.get("fill_policy_version", "1.0.0"),
            
            # Data provenance
            data_source_id=data.get("data_source_id", "duckdb_live"),
            data_version=data.get("data_version"),
            candle_policy=data.get("candle_policy", "closed_only"),
            
            # Randomness
            seed=data.get("seed"),
            
            # Category & semantics
            category=data.get("category", "_validation"),
            is_promotable=data.get("is_promotable", False),
            allows_overwrite=data.get("allows_overwrite", True),
            attempt_id=data.get("attempt_id"),
            
            # Warmup/delay audit trail
            # RENAMED: computed_warmup_by_role → computed_lookback_bars_by_role (breaking change)
            computed_lookback_bars_by_role=data.get("computed_lookback_bars_by_role"),
            computed_delay_bars_by_role=data.get("computed_delay_bars_by_role"),
            warmup_tool_calls=data.get("warmup_tool_calls"),
            
            # Phase 6: Engine-truth evaluation start
            eval_start_ts_ms=data.get("eval_start_ts_ms"),
            equity_timestamp_column=data.get("equity_timestamp_column", "ts_ms"),
            
            # Audit trail
            created_at_utc=data.get("created_at_utc", ""),

            # Schema version (use current if not present - backward compat)
            schema_version=data.get("schema_version", MANIFEST_SCHEMA_VERSION),
        )
    
    @classmethod
    def load_json(cls, path: Path) -> "RunManifest":
        """Load manifest from JSON file."""
        data = json.loads(path.read_text())
        return cls.from_dict(data)
    
    def verify_folder_hash(self, folder_name: str) -> tuple[bool, str]:
        """
        Verify that folder name matches the short hash.
        
        VERIFICATION RULES:
        1. folder_name == short_hash
        2. full_hash.startswith(short_hash)
        3. len(short_hash) == short_hash_length
        
        Args:
            folder_name: The folder name (should be N-char hash)
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        errors = []
        
        # Rule 1: folder name == short_hash
        if folder_name != self.short_hash:
            errors.append(
                f"Folder name '{folder_name}' does not match "
                f"manifest short_hash '{self.short_hash}'"
            )
        
        # Rule 2: full_hash starts with short_hash
        if not self.full_hash.startswith(self.short_hash):
            errors.append(
                f"full_hash '{self.full_hash[:16]}...' does not start with "
                f"short_hash '{self.short_hash}' - POSSIBLE COLLISION"
            )
        
        # Rule 3: short_hash length matches declared length
        if len(self.short_hash) != self.short_hash_length:
            errors.append(
                f"short_hash length {len(self.short_hash)} does not match "
                f"declared short_hash_length {self.short_hash_length}"
            )
        
        if errors:
            return False, "; ".join(errors)
        return True, ""
    
    def verify_hash_integrity(self) -> tuple[bool, str]:
        """
        Verify internal hash consistency.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        errors = []
        
        # Verify full_hash is 64 chars (SHA256)
        if len(self.full_hash) != 64:
            errors.append(f"full_hash should be 64 chars, got {len(self.full_hash)}")
        
        # Verify full_hash starts with short_hash
        if not self.full_hash.startswith(self.short_hash):
            errors.append("full_hash does not start with short_hash - COLLISION DETECTED")
        
        # Verify short_hash_length
        if len(self.short_hash) != self.short_hash_length:
            errors.append(
                f"short_hash length mismatch: {len(self.short_hash)} vs {self.short_hash_length}"
            )
        
        # Verify hash algorithm
        if self.hash_algorithm != "sha256":
            errors.append(f"Unsupported hash algorithm: {self.hash_algorithm}")
        
        if errors:
            return False, "; ".join(errors)
        return True, ""


@dataclass
class ManifestVerificationResult:
    """Result of manifest verification."""
    is_valid: bool
    folder_matches: bool
    hash_integrity: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def verify_run_folder(run_folder: Path) -> tuple[bool, str]:
    """
    Verify a run folder's manifest matches its folder name and internal consistency.
    
    VERIFICATION STEPS:
    1. run_manifest.json exists
    2. Manifest loads without error
    3. Folder name == manifest.short_hash
    4. manifest.full_hash.startswith(manifest.short_hash)
    5. len(manifest.short_hash) == manifest.short_hash_length
    
    On collision detection: FAIL HARD with clear error message.
    
    Args:
        run_folder: Path to the run folder
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    manifest_path = run_folder / "run_manifest.json"
    
    # Step 1: Check manifest exists
    if not manifest_path.exists():
        return False, f"Missing run_manifest.json in {run_folder}"
    
    # Step 2: Load manifest
    try:
        manifest = RunManifest.load_json(manifest_path)
    except Exception as e:
        return False, f"Failed to load manifest: {e}"
    
    # Step 3: Verify hash integrity (internal consistency)
    integrity_ok, integrity_error = manifest.verify_hash_integrity()
    if not integrity_ok:
        return False, f"Hash integrity check failed: {integrity_error}"
    
    # Step 4: Verify folder name matches manifest
    folder_name = run_folder.name
    folder_ok, folder_error = manifest.verify_folder_hash(folder_name)
    if not folder_ok:
        return False, f"Folder verification failed: {folder_error}"
    
    return True, ""


# =============================================================================
# Artifact Validation
# =============================================================================

@dataclass
class ArtifactValidationResult:
    """Result of artifact validation."""
    passed: bool
    run_folder: Path
    files_found: set[str] = field(default_factory=set)
    files_missing: set[str] = field(default_factory=set)
    column_errors: dict[str, list[str]] = field(default_factory=dict)
    result_field_errors: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    # Phase 2: Pipeline signature validation
    pipeline_signature_valid: bool | None = None
    pipeline_signature_errors: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "passed": self.passed,
            "run_folder": str(self.run_folder),
            "files_found": sorted(self.files_found),
            "files_missing": sorted(self.files_missing),
            "column_errors": self.column_errors,
            "result_field_errors": self.result_field_errors,
            "errors": self.errors,
            "pipeline_signature_valid": self.pipeline_signature_valid,
            "pipeline_signature_errors": self.pipeline_signature_errors,
        }
    
    def print_summary(self) -> None:
        """Print validation summary to console."""
        status_icon = "[OK]" if self.passed else "[FAIL]"
        print(f"\n{status_icon} Artifact Export Gate: {'PASSED' if self.passed else 'FAILED'}")
        print(f"   Folder: {self.run_folder}")
        print(f"   Files found: {len(self.files_found)} / {len(REQUIRED_FILES)} required")
        
        if self.files_missing:
            print(f"   [ERR] Missing files: {', '.join(sorted(self.files_missing))}")
        
        if self.column_errors:
            for file, errors in self.column_errors.items():
                for err in errors:
                    print(f"   [ERR] {file}: {err}")
        
        if self.result_field_errors:
            for err in self.result_field_errors:
                print(f"   [ERR] result.json: {err}")
        
        if self.errors:
            for err in self.errors:
                print(f"   [ERR] {err}")
        
        # Phase 2: Pipeline signature validation status (HARD FAIL if invalid)
        if self.pipeline_signature_valid is not None:
            sig_icon = "[OK]" if self.pipeline_signature_valid else "[ERR]"
            print(f"   {sig_icon} Pipeline Signature: {'VALID' if self.pipeline_signature_valid else 'INVALID (HARD FAIL)'}")
            for err in self.pipeline_signature_errors:
                print(f"      - {err}")
        
        print()


def validate_artifacts(run_folder: Path) -> ArtifactValidationResult:
    """
    Validate that artifacts in a run folder meet standards.
    
    Args:
        run_folder: Path to the run folder
        
    Returns:
        ArtifactValidationResult with validation results
    """
    result = ArtifactValidationResult(
        passed=True,
        run_folder=run_folder,
    )
    
    # Check folder exists
    if not run_folder.exists():
        result.passed = False
        result.errors.append(f"Run folder does not exist: {run_folder}")
        return result
    
    # Check required files exist
    for filename in REQUIRED_FILES:
        file_path = run_folder / filename
        if file_path.exists():
            result.files_found.add(filename)
        else:
            result.files_missing.add(filename)
    
    if result.files_missing:
        result.passed = False
        result.errors.append(f"Missing required files: {', '.join(sorted(result.files_missing))}")
    
    # Validate trades.parquet columns (Phase 3.2: Parquet primary)
    trades_path = run_folder / "trades.parquet"
    if trades_path.exists():
        try:
            import pandas as pd
            import pyarrow.parquet as pq
            # Read schema only (efficient)
            schema = pq.read_schema(trades_path)
            actual_cols = set(schema.names)
            missing_cols = REQUIRED_TRADES_COLUMNS - actual_cols
            if missing_cols:
                result.column_errors["trades.parquet"] = [
                    f"Missing required columns: {', '.join(sorted(missing_cols))}"
                ]
                result.passed = False
        except Exception as e:
            result.column_errors["trades.parquet"] = [f"Failed to read: {str(e)}"]
            result.passed = False
    
    # Validate equity.parquet columns (Phase 3.2: Parquet primary)
    equity_path = run_folder / "equity.parquet"
    if equity_path.exists():
        try:
            import pyarrow.parquet as pq
            schema = pq.read_schema(equity_path)
            actual_cols = set(schema.names)
            missing_cols = REQUIRED_EQUITY_COLUMNS - actual_cols
            if missing_cols:
                result.column_errors["equity.parquet"] = [
                    f"Missing required columns: {', '.join(sorted(missing_cols))}"
                ]
                result.passed = False
        except Exception as e:
            result.column_errors["equity.parquet"] = [f"Failed to read: {str(e)}"]
            result.passed = False
    
    # Validate result.json fields
    result_path = run_folder / "result.json"
    if result_path.exists():
        try:
            with open(result_path, "r", encoding="utf-8") as f:
                result_data = json.load(f)
            
            missing_fields = REQUIRED_RESULT_FIELDS - set(result_data.keys())
            if missing_fields:
                result.result_field_errors.append(
                    f"Missing required fields: {', '.join(sorted(missing_fields))}"
                )
                result.passed = False
        except Exception as e:
            result.result_field_errors.append(f"Failed to read: {str(e)}")
            result.passed = False
    
    # Validate pipeline_signature.json (Phase 2: Production pipeline verification)
    # HARD FAILURE: Any pipeline signature variance fails validation
    # This enables future drift detection by ensuring consistent pipeline execution
    signature_path = run_folder / "pipeline_signature.json"
    if signature_path.exists():
        try:
            from .pipeline_signature import PipelineSignature
            with open(signature_path, "r", encoding="utf-8") as f:
                sig_data = json.load(f)
            
            # Create PipelineSignature from dict and validate
            sig = PipelineSignature(**sig_data)
            sig_errors = sig.validate()
            if sig_errors:
                result.pipeline_signature_valid = False
                result.pipeline_signature_errors = sig_errors
                result.passed = False  # HARD FAIL - pipeline must be valid
            else:
                result.pipeline_signature_valid = True
        except Exception as e:
            result.pipeline_signature_valid = False
            result.pipeline_signature_errors = [f"Failed to validate: {str(e)}"]
            result.passed = False  # HARD FAIL - must be able to validate
    
    return result


def validate_artifact_path_config(config: ArtifactPathConfig) -> list[str]:
    """
    Validate artifact path configuration before run.
    
    Returns:
        List of error messages (empty if valid)
    """
    errors = []
    
    if not config.play_id:
        errors.append("play_id is required")
    if not config.universe_id:
        errors.append("universe_id is required")
    if not config.tf_exec:
        errors.append("tf_exec is required")
    if not config.window_start:
        errors.append("window_start is required")
    if not config.window_end:
        errors.append("window_end is required")
    
    return errors


# =============================================================================
# Results Summary
# =============================================================================

@dataclass
class ResultsSummary:
    """Summary of backtest results with comprehensive analytics."""
    # Identity
    play_id: str
    symbol: str
    tf_exec: str
    window_start: datetime
    window_end: datetime
    run_id: str
    
    # Core Metrics
    trades_count: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    net_pnl_usdt: float = 0.0
    net_return_pct: float = 0.0
    gross_profit_usdt: float = 0.0
    gross_loss_usdt: float = 0.0
    max_drawdown_usdt: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_duration_bars: int = 0
    
    # Risk-Adjusted Metrics
    sharpe: float = 0.0
    sortino: float = 0.0
    calmar: float = 0.0
    profit_factor: float = 0.0
    
    # Extended Trade Analytics
    avg_win_usdt: float = 0.0
    avg_loss_usdt: float = 0.0
    largest_win_usdt: float = 0.0
    largest_loss_usdt: float = 0.0
    avg_trade_duration_bars: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    expectancy_usdt: float = 0.0
    payoff_ratio: float = 0.0
    recovery_factor: float = 0.0
    total_fees_usdt: float = 0.0
    
    # Long/Short Breakdown
    long_trades: int = 0
    short_trades: int = 0
    long_win_rate: float = 0.0
    short_win_rate: float = 0.0
    long_pnl: float = 0.0
    short_pnl: float = 0.0
    
    # Time Metrics
    total_bars: int = 0
    bars_in_position: int = 0
    time_in_market_pct: float = 0.0

    # Risk/Position Config
    leverage: int = 1
    initial_equity: float = 10000.0

    # Metadata
    artifact_path: str = ""
    run_duration_seconds: float = 0.0
    
    # Gate D required fields (for artifact validation)
    play_hash: str = ""
    pipeline_version: str = ""
    resolved_idea_path: str = ""
    
    # Determinism hashes (Phase 3 - hash-based verification)
    trades_hash: str = ""     # SHA256 hash of trades.parquet content
    equity_hash: str = ""     # SHA256 hash of equity.parquet content
    run_hash: str = ""        # Combined hash (trades + equity + play)

    # Stop fields (terminal risk events)
    stopped_early: bool = False
    stop_reason: str | None = None

    # Benchmark/Alpha
    benchmark_return_pct: float = 0.0
    alpha_pct: float = 0.0

    # Tail Risk
    skewness: float = 0.0
    kurtosis: float = 0.0
    var_95_pct: float = 0.0
    cvar_95_pct: float = 0.0

    # Extended Risk
    ulcer_index: float = 0.0
    omega_ratio: float = 0.0

    # Leverage / Margin
    avg_leverage_used: float = 0.0
    max_gross_exposure_pct: float = 0.0

    # Trade Quality (MAE/MFE)
    mae_avg_pct: float = 0.0
    mfe_avg_pct: float = 0.0

    # Entry Friction
    entry_attempts: int = 0
    entry_rejections: int = 0
    entry_rejection_rate: float = 0.0

    # Margin Stress
    margin_calls: int = 0
    min_margin_ratio: float = 1.0
    closest_liquidation_pct: float = 100.0

    # Funding
    total_funding_paid_usdt: float = 0.0
    total_funding_received_usdt: float = 0.0
    net_funding_usdt: float = 0.0
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            # Identity
            "play_id": self.play_id,
            "symbol": self.symbol,
            "tf_exec": self.tf_exec,
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "run_id": self.run_id,
            # Core Metrics
            "trades_count": self.trades_count,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": round(self.win_rate, 4),
            "net_pnl_usdt": round(self.net_pnl_usdt, 2),
            "net_return_pct": round(self.net_return_pct, 2),
            "gross_profit_usdt": round(self.gross_profit_usdt, 2),
            "gross_loss_usdt": round(self.gross_loss_usdt, 2),
            "max_drawdown_usdt": round(self.max_drawdown_usdt, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "max_drawdown_duration_bars": self.max_drawdown_duration_bars,
            # Risk-Adjusted Metrics
            "sharpe": round(self.sharpe, 2),
            "sortino": round(self.sortino, 2),
            "calmar": round(self.calmar, 2),
            "profit_factor": round(self.profit_factor, 2),
            # Extended Trade Analytics
            "avg_win_usdt": round(self.avg_win_usdt, 2),
            "avg_loss_usdt": round(self.avg_loss_usdt, 2),
            "largest_win_usdt": round(self.largest_win_usdt, 2),
            "largest_loss_usdt": round(self.largest_loss_usdt, 2),
            "avg_trade_duration_bars": round(self.avg_trade_duration_bars, 2),
            "max_consecutive_wins": self.max_consecutive_wins,
            "max_consecutive_losses": self.max_consecutive_losses,
            "expectancy_usdt": round(self.expectancy_usdt, 2),
            "payoff_ratio": round(self.payoff_ratio, 2),
            "recovery_factor": round(self.recovery_factor, 2),
            "total_fees_usdt": round(self.total_fees_usdt, 2),
            # Long/Short Breakdown
            "long_trades": self.long_trades,
            "short_trades": self.short_trades,
            "long_win_rate": round(self.long_win_rate, 2),
            "short_win_rate": round(self.short_win_rate, 2),
            "long_pnl": round(self.long_pnl, 2),
            "short_pnl": round(self.short_pnl, 2),
            # Time Metrics
            "total_bars": self.total_bars,
            "bars_in_position": self.bars_in_position,
            "time_in_market_pct": round(self.time_in_market_pct, 2),
            # Risk/Position Config
            "leverage": self.leverage,
            "initial_equity": round(self.initial_equity, 2),
            # Metadata
            "artifact_path": self.artifact_path,
            "run_duration_seconds": round(self.run_duration_seconds, 2),
            # Gate D required fields
            "play_hash": self.play_hash,
            "pipeline_version": self.pipeline_version,
            "resolved_idea_path": self.resolved_idea_path,
            # Determinism hashes (Phase 3)
            "trades_hash": self.trades_hash,
            "equity_hash": self.equity_hash,
            "run_hash": self.run_hash,
            # Stop fields
            "stopped_early": self.stopped_early,
            "stop_reason": self.stop_reason,
            # Benchmark/Alpha
            "benchmark_return_pct": round(self.benchmark_return_pct, 2),
            "alpha_pct": round(self.alpha_pct, 2),
            # Tail Risk
            "skewness": round(self.skewness, 4),
            "kurtosis": round(self.kurtosis, 4),
            "var_95_pct": round(self.var_95_pct, 4),
            "cvar_95_pct": round(self.cvar_95_pct, 4),
            # Extended Risk
            "ulcer_index": round(self.ulcer_index, 4),
            "omega_ratio": round(self.omega_ratio, 2),
            # Leverage / Margin
            "avg_leverage_used": round(self.avg_leverage_used, 2),
            "max_gross_exposure_pct": round(self.max_gross_exposure_pct, 2),
            # Trade Quality
            "mae_avg_pct": round(self.mae_avg_pct, 4),
            "mfe_avg_pct": round(self.mfe_avg_pct, 4),
            # Entry Friction
            "entry_attempts": self.entry_attempts,
            "entry_rejections": self.entry_rejections,
            "entry_rejection_rate": round(self.entry_rejection_rate, 4),
            # Margin Stress
            "margin_calls": self.margin_calls,
            "min_margin_ratio": round(self.min_margin_ratio, 4),
            "closest_liquidation_pct": round(self.closest_liquidation_pct, 2),
            # Funding
            "total_funding_paid_usdt": round(self.total_funding_paid_usdt, 2),
            "total_funding_received_usdt": round(self.total_funding_received_usdt, 2),
            "net_funding_usdt": round(self.net_funding_usdt, 2),
        }
    
    def write_json(self, path: Path) -> None:
        """Write summary to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, sort_keys=True)
    
    def print_summary(self) -> None:
        """Print comprehensive summary to console."""
        window_days = (self.window_end - self.window_start).days
        pnl_icon = "[+]" if self.net_pnl_usdt >= 0 else "[-]"

        print("\n" + "=" * 60)
        print("  BACKTEST RESULTS SUMMARY")
        print("=" * 60)
        print(f"  Play:    {self.play_id}")
        print(f"  Symbol:      {self.symbol}")
        print(f"  Timeframe:   {self.tf_exec}")
        print(f"  Window:      {self.window_start.date()} -> {self.window_end.date()} ({window_days}d)")
        print(f"  Leverage:    {self.leverage}x | Equity: ${self.initial_equity:,.0f}")
        print("-" * 60)

        # Trade Summary
        print(f"  Trades:      {self.trades_count} ({self.winning_trades}W / {self.losing_trades}L)")
        print(f"  Win Rate:    {self.win_rate * 100:.1f}%")
        print(f"  {pnl_icon} Net PnL:    {self.net_pnl_usdt:+.2f} USDT ({self.net_return_pct:+.1f}%)")
        print(f"  Max DD:      {self.max_drawdown_usdt:.2f} USDT ({self.max_drawdown_pct * 100:.1f}%)")
        if self.ulcer_index > 0:
            print(f"  Ulcer Index: {self.ulcer_index:.4f}")
        if self.recovery_factor != 0:
            print(f"  Recovery:    {self.recovery_factor:.2f}")
        print("-" * 60)

        # Risk-Adjusted Metrics
        print(f"  Sharpe:      {self.sharpe:.2f}")
        print(f"  Sortino:     {self.sortino:.2f}")
        print(f"  Calmar:      {self.calmar:.2f}")
        print(f"  Profit Factor: {self.profit_factor:.2f}")
        if self.omega_ratio != 0:
            print(f"  Omega Ratio: {self.omega_ratio:.2f}")
        print("-" * 60)

        # Trade Analytics
        print(f"  Avg Win:     {self.avg_win_usdt:.2f} USDT")
        print(f"  Avg Loss:    {self.avg_loss_usdt:.2f} USDT")
        print(f"  Largest Win: {self.largest_win_usdt:.2f} USDT")
        print(f"  Largest Loss:{self.largest_loss_usdt:.2f} USDT")
        print(f"  Payoff Ratio: {self.payoff_ratio:.2f}")
        print(f"  Expectancy:  {self.expectancy_usdt:.2f} USDT/trade")
        print(f"  Max Consec:  {self.max_consecutive_wins}W / {self.max_consecutive_losses}L")

        # Trade Quality (MAE/MFE) — show if non-zero
        if self.mae_avg_pct != 0 or self.mfe_avg_pct != 0:
            print(f"  MAE avg:     {self.mae_avg_pct:.2f}%")
            print(f"  MFE avg:     {self.mfe_avg_pct:.2f}%")
        print("-" * 60)

        # Benchmark / Alpha — show if non-zero
        if self.benchmark_return_pct != 0 or self.alpha_pct != 0:
            print(f"  Benchmark:   {self.benchmark_return_pct:+.2f}%")
            print(f"  Alpha:       {self.alpha_pct:+.2f}%")
            print("-" * 60)

        # Tail Risk — show if computed
        if self.skewness != 0 or self.kurtosis != 0:
            print(f"  Skewness:    {self.skewness:.4f}")
            print(f"  Kurtosis:    {self.kurtosis:.4f}")
            print(f"  VaR 95%:     {self.var_95_pct:.4f}%")
            print(f"  CVaR 95%:    {self.cvar_95_pct:.4f}%")
            print("-" * 60)

        # Long/Short Breakdown
        if self.long_trades > 0 or self.short_trades > 0:
            print(f"  Long:        {self.long_trades} trades, {self.long_win_rate:.1f}% WR, {self.long_pnl:+.2f} USDT")
            print(f"  Short:       {self.short_trades} trades, {self.short_win_rate:.1f}% WR, {self.short_pnl:+.2f} USDT")
            print("-" * 60)

        # Leverage / Margin — show only if leverage > 1
        if self.leverage > 1:
            print(f"  Avg Leverage:{self.avg_leverage_used:.2f}x")
            print(f"  Max Exposure:{self.max_gross_exposure_pct:.1f}%")
            if self.closest_liquidation_pct < 100:
                print(f"  Closest Liq: {self.closest_liquidation_pct:.1f}%")
            if self.margin_calls > 0:
                print(f"  Margin Calls:{self.margin_calls}")
            print("-" * 60)

        # Entry Friction — show only if rejections occurred
        if self.entry_rejections > 0:
            print(f"  Entry Tries: {self.entry_attempts}")
            print(f"  Rejections:  {self.entry_rejections} ({self.entry_rejection_rate * 100:.1f}%)")
            print("-" * 60)

        # Funding — show only if any funding
        if self.total_funding_paid_usdt != 0 or self.total_funding_received_usdt != 0:
            print(f"  Funding Paid:{self.total_funding_paid_usdt:.2f} USDT")
            print(f"  Funding Recv:{self.total_funding_received_usdt:.2f} USDT")
            print(f"  Net Funding: {self.net_funding_usdt:+.2f} USDT")
            print("-" * 60)

        # Time Metrics
        print(f"  Time in Mkt: {self.time_in_market_pct:.1f}% ({self.bars_in_position}/{self.total_bars} bars)")
        print(f"  Fees:        {self.total_fees_usdt:.2f} USDT")
        print("-" * 60)
        print(f"  Artifacts:   {self.artifact_path}")
        if self.play_hash or self.trades_hash or self.run_hash:
            print(f"  Play Hash:   {self.play_hash[:8] if self.play_hash else '--'}")
            print(f"  Trades Hash: {self.trades_hash[:8] if self.trades_hash else '--'}")
            print(f"  Run Hash:    {self.run_hash[:8] if self.run_hash else '--'}")
        print("=" * 60 + "\n")


def compute_results_summary(
    play_id: str,
    symbol: str,
    tf_exec: str,
    window_start: datetime,
    window_end: datetime,
    run_id: str,
    trades: list[dict[str, Any]],
    equity_curve: list[dict[str, Any]],
    artifact_path: str = "",
    run_duration_seconds: float = 0.0,
    # Gate D required fields
    play_hash: str = "",
    pipeline_version: str = "",
    resolved_idea_path: str = "",
    # Determinism hashes (Phase 3)
    trades_hash: str = "",
    equity_hash: str = "",
    run_hash: str = "",
    # Optional pre-computed metrics from BacktestMetrics
    metrics: Any | None = None,  # BacktestMetrics type hint avoided for circular import
    # Risk/Position Config from Play
    leverage: int = 1,
    initial_equity: float = 10000.0,
    # Stop fields (terminal risk events)
    stopped_early: bool = False,
    stop_reason: str | None = None,
) -> ResultsSummary:
    """
    Compute results summary from trades and equity curve.
    
    Args:
        play_id: Play identifier
        symbol: Trading symbol
        tf_exec: Execution timeframe
        window_start: Backtest window start
        window_end: Backtest window end
        run_id: Run identifier
        trades: List of trade dicts with pnl_usdt field
        equity_curve: List of equity point dicts with equity field
        artifact_path: Path to artifact folder
        run_duration_seconds: Run duration
        play_hash: Play hash for determinism tracking
        pipeline_version: Pipeline version string
        resolved_idea_path: Path where Play was loaded from
        trades_hash: SHA256 hash of trades output
        equity_hash: SHA256 hash of equity curve output
        run_hash: Combined hash of trades + equity for determinism
        metrics: Pre-computed BacktestMetrics object (if provided, uses these values)
        
    Returns:
        ResultsSummary with computed metrics
    """
    summary = ResultsSummary(
        play_id=play_id,
        symbol=symbol,
        tf_exec=tf_exec,
        window_start=window_start,
        window_end=window_end,
        run_id=run_id,
        artifact_path=artifact_path,
        run_duration_seconds=run_duration_seconds,
        play_hash=play_hash,
        pipeline_version=pipeline_version,
        resolved_idea_path=resolved_idea_path,
        trades_hash=trades_hash,
        equity_hash=equity_hash,
        run_hash=run_hash,
        leverage=leverage,
        initial_equity=initial_equity,
        stopped_early=stopped_early,
        stop_reason=stop_reason,
    )
    
    # If pre-computed metrics provided, use them directly
    if metrics is not None:
        summary.trades_count = metrics.total_trades
        summary.winning_trades = metrics.win_count
        summary.losing_trades = metrics.loss_count
        summary.win_rate = metrics.win_rate / 100.0  # Convert from % to decimal
        summary.net_pnl_usdt = metrics.net_profit
        summary.net_return_pct = metrics.net_return_pct
        summary.gross_profit_usdt = metrics.gross_profit
        summary.gross_loss_usdt = -metrics.gross_loss  # Store as negative
        summary.max_drawdown_usdt = metrics.max_drawdown_abs
        summary.max_drawdown_pct = metrics.max_drawdown_pct / 100.0  # Convert from % to decimal
        summary.max_drawdown_duration_bars = metrics.max_drawdown_duration_bars
        # Risk-adjusted
        summary.sharpe = metrics.sharpe
        summary.sortino = metrics.sortino
        summary.calmar = metrics.calmar
        summary.profit_factor = metrics.profit_factor
        # Extended analytics
        summary.avg_win_usdt = metrics.avg_win_usdt
        summary.avg_loss_usdt = metrics.avg_loss_usdt
        summary.largest_win_usdt = metrics.largest_win_usdt
        summary.largest_loss_usdt = metrics.largest_loss_usdt
        summary.avg_trade_duration_bars = metrics.avg_trade_duration_bars
        summary.max_consecutive_wins = metrics.max_consecutive_wins
        summary.max_consecutive_losses = metrics.max_consecutive_losses
        summary.expectancy_usdt = metrics.expectancy_usdt
        summary.payoff_ratio = metrics.payoff_ratio
        summary.recovery_factor = metrics.recovery_factor
        summary.total_fees_usdt = metrics.total_fees
        # Long/short
        summary.long_trades = metrics.long_trades
        summary.short_trades = metrics.short_trades
        summary.long_win_rate = metrics.long_win_rate
        summary.short_win_rate = metrics.short_win_rate
        summary.long_pnl = metrics.long_pnl
        summary.short_pnl = metrics.short_pnl
        # Time metrics
        summary.total_bars = metrics.total_bars
        summary.bars_in_position = metrics.bars_in_position
        summary.time_in_market_pct = metrics.time_in_market_pct
        # Extended metrics (use getattr for compatibility with SimpleNamespace)
        summary.benchmark_return_pct = getattr(metrics, "benchmark_return_pct", 0.0)
        summary.alpha_pct = getattr(metrics, "alpha_pct", 0.0)
        summary.skewness = getattr(metrics, "skewness", 0.0)
        summary.kurtosis = getattr(metrics, "kurtosis", 0.0)
        summary.var_95_pct = getattr(metrics, "var_95_pct", 0.0)
        summary.cvar_95_pct = getattr(metrics, "cvar_95_pct", 0.0)
        summary.ulcer_index = getattr(metrics, "ulcer_index", 0.0)
        summary.omega_ratio = getattr(metrics, "omega_ratio", 0.0)
        summary.avg_leverage_used = getattr(metrics, "avg_leverage_used", 0.0)
        summary.max_gross_exposure_pct = getattr(metrics, "max_gross_exposure_pct", 0.0)
        summary.mae_avg_pct = getattr(metrics, "mae_avg_pct", 0.0)
        summary.mfe_avg_pct = getattr(metrics, "mfe_avg_pct", 0.0)
        summary.entry_attempts = getattr(metrics, "entry_attempts", 0)
        summary.entry_rejections = getattr(metrics, "entry_rejections", 0)
        summary.entry_rejection_rate = getattr(metrics, "entry_rejection_rate", 0.0)
        summary.margin_calls = getattr(metrics, "margin_calls", 0)
        summary.min_margin_ratio = getattr(metrics, "min_margin_ratio", 1.0)
        summary.closest_liquidation_pct = getattr(metrics, "closest_liquidation_pct", 100.0)
        summary.total_funding_paid_usdt = getattr(metrics, "total_funding_paid_usdt", 0.0)
        summary.total_funding_received_usdt = getattr(metrics, "total_funding_received_usdt", 0.0)
        summary.net_funding_usdt = getattr(metrics, "net_funding_usdt", 0.0)
        return summary
    
    raise ValueError(
        "metrics parameter is required. Pass BacktestMetrics from the runner. "
        "Legacy compute-from-trades path has been removed."
    )
