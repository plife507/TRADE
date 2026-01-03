"""
Run manifest writer.

Writes run_manifest.json with:
- artifact_version
- config hash
- git commit (if available)
- data window [load_start, load_end]
- DataHealthCheck report summary
- symbol/tf_mapping
"""

import json
import hashlib
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


def get_git_commit() -> str | None:
    """Get current git commit hash, or None if not in a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()[:12]  # Short hash
    except Exception:
        pass
    return None


def compute_config_hash(config_dict: dict) -> str:
    """Compute stable hash of config dict."""
    # Sort keys for stability
    json_str = json.dumps(config_dict, sort_keys=True, default=str)
    return hashlib.sha256(json_str.encode()).hexdigest()[:16]


class ManifestWriter:
    """
    Writes run_manifest.json for a backtest run.
    
    The manifest captures all metadata needed to reproduce the run.
    """
    
    def __init__(
        self,
        run_dir: Path,
        artifact_version: str = "0.1.0-dev",
    ):
        """
        Initialize manifest writer.
        
        Args:
            run_dir: Directory for run artifacts
            artifact_version: Version string for artifact schema
        """
        self.run_dir = Path(run_dir)
        self.artifact_version = artifact_version
        self._manifest: dict[str, Any] = {
            "artifact_version": artifact_version,
            "created_at": datetime.now().isoformat(),
        }
    
    def set_run_info(
        self,
        run_id: str,
        system_id: str,
        symbol: str,
        tf_mapping: dict[str, str],
    ) -> None:
        """Set basic run information."""
        self._manifest.update({
            "run_id": run_id,
            "system_id": system_id,
            "symbol": symbol,
            "tf_mapping": tf_mapping,
        })
    
    def set_data_window(
        self,
        load_start: datetime,
        load_end: datetime,
        test_start: datetime | None = None,
        test_end: datetime | None = None,
    ) -> None:
        """Set data window information."""
        self._manifest["data_window"] = {
            "load_start": load_start.isoformat(),
            "load_end": load_end.isoformat(),
            "test_start": test_start.isoformat() if test_start else None,
            "test_end": test_end.isoformat() if test_end else None,
        }
    
    def set_config(self, config_dict: dict) -> None:
        """Set config and compute hash."""
        self._manifest["config_hash"] = compute_config_hash(config_dict)
        self._manifest["config"] = config_dict
    
    def set_health_report(self, health_report: dict) -> None:
        """Set DataHealthCheck report summary."""
        self._manifest["health_report"] = {
            "passed": health_report.get("passed", False),
            "coverage_issues": health_report.get("coverage_issues", []),
            "total_missing_bars": health_report.get("total_missing_bars", 0),
            "sanity_issues_count": len(health_report.get("sanity_issues", [])),
        }
    
    def set_git_info(self) -> None:
        """Set git commit info."""
        commit = get_git_commit()
        if commit:
            self._manifest["git_commit"] = commit
    
    def add_metadata(self, key: str, value: Any) -> None:
        """Add arbitrary metadata."""
        if "metadata" not in self._manifest:
            self._manifest["metadata"] = {}
        self._manifest["metadata"][key] = value
    
    def write(self) -> Path:
        """
        Write manifest to run_dir/run_manifest.json.
        
        Returns:
            Path to written manifest file
        """
        self.run_dir.mkdir(parents=True, exist_ok=True)
        
        # Add final timestamp
        self._manifest["written_at"] = datetime.now().isoformat()
        
        manifest_path = self.run_dir / "run_manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(self._manifest, f, indent=2, default=str, sort_keys=True)
        
        return manifest_path
    
    def get_manifest(self) -> dict:
        """Get manifest dict (for testing/inspection)."""
        return dict(self._manifest)

