"""
History management module for BacktestEngine.

This module handles rolling history window management:
- HistoryManager: Class to manage history state and operations
- parse_history_config_impl: Parse HistoryConfig from SystemConfig
- update_history_impl: Update rolling history windows
- is_history_ready_impl: Check if history windows are filled
- get_history_tuples_impl: Get immutable history tuples for snapshot

The BacktestEngine delegates to these functions/class, maintaining the same public API.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .runtime.types import (
    Bar as CanonicalBar,
    FeatureSnapshot,
    HistoryConfig,
    DEFAULT_HISTORY_CONFIG,
)

if TYPE_CHECKING:
    from .system_config import SystemConfig


def parse_history_config_impl(config: "SystemConfig") -> HistoryConfig:
    """
    Parse HistoryConfig from system config.

    Looks for optional 'history' section in params or config.

    Args:
        config: System configuration

    Returns:
        HistoryConfig (default if not specified)
    """
    # Check params for history config
    params = config.params
    history_raw = params.get("history", {})

    if not history_raw:
        return DEFAULT_HISTORY_CONFIG

    return HistoryConfig(
        bars_exec_count=int(history_raw.get("bars_exec_count", 0)),
        features_exec_count=int(history_raw.get("features_exec_count", 0)),
        features_high_tf_count=int(history_raw.get("features_high_tf_count", 0)),
        features_med_tf_count=int(history_raw.get("features_med_tf_count", 0)),
    )


class HistoryManager:
    """
    Manages rolling history windows for strategy evaluation.

    Encapsulates history state and provides methods to update, check, and access
    history data. Used by BacktestEngine to track bar and feature history.
    """

    def __init__(self, history_config: HistoryConfig):
        """
        Initialize HistoryManager with configuration.

        Args:
            history_config: HistoryConfig specifying window sizes
        """
        self._config = history_config

        # Rolling history windows (mutable lists, converted to tuples for snapshot)
        self._history_bars_exec: list[CanonicalBar] = []
        self._history_features_exec: list[FeatureSnapshot] = []
        self._history_features_htf: list[FeatureSnapshot] = []
        self._history_features_mtf: list[FeatureSnapshot] = []

    @property
    def config(self) -> HistoryConfig:
        """Get the history configuration."""
        return self._config

    @property
    def bars_exec(self) -> list[CanonicalBar]:
        """Get current exec bar history."""
        return self._history_bars_exec

    @property
    def features_exec(self) -> list[FeatureSnapshot]:
        """Get current exec feature history."""
        return self._history_features_exec

    @property
    def features_htf(self) -> list[FeatureSnapshot]:
        """Get current HTF feature history."""
        return self._history_features_htf

    @property
    def features_mtf(self) -> list[FeatureSnapshot]:
        """Get current MTF feature history."""
        return self._history_features_mtf

    def update(
        self,
        bar: CanonicalBar,
        features_exec: FeatureSnapshot,
        htf_updated: bool,
        mtf_updated: bool,
        features_htf: FeatureSnapshot | None,
        features_mtf: FeatureSnapshot | None,
    ) -> None:
        """
        Update rolling history windows.

        Called after each bar close, before snapshot build.
        Maintains bounded windows per HistoryConfig.

        Args:
            bar: Current exec-TF bar
            features_exec: Current exec-TF features
            htf_updated: Whether HTF cache was updated this step
            mtf_updated: Whether MTF cache was updated this step
            features_htf: Current HTF features (if updated)
            features_mtf: Current MTF features (if updated)
        """
        config = self._config

        # Update exec bar history
        if config.bars_exec_count > 0:
            self._history_bars_exec.append(bar)
            # Trim to max size (keep most recent)
            if len(self._history_bars_exec) > config.bars_exec_count:
                self._history_bars_exec = self._history_bars_exec[-config.bars_exec_count:]

        # Update exec feature history
        if config.features_exec_count > 0 and features_exec.ready:
            self._history_features_exec.append(features_exec)
            if len(self._history_features_exec) > config.features_exec_count:
                self._history_features_exec = self._history_features_exec[-config.features_exec_count:]

        # Update HTF feature history (only on HTF close)
        if config.features_high_tf_count > 0 and htf_updated and features_htf and features_htf.ready:
            self._history_features_htf.append(features_htf)
            if len(self._history_features_htf) > config.features_high_tf_count:
                self._history_features_htf = self._history_features_htf[-config.features_high_tf_count:]

        # Update MTF feature history (only on MTF close)
        if config.features_med_tf_count > 0 and mtf_updated and features_mtf and features_mtf.ready:
            self._history_features_mtf.append(features_mtf)
            if len(self._history_features_mtf) > config.features_med_tf_count:
                self._history_features_mtf = self._history_features_mtf[-config.features_med_tf_count:]

    def is_ready(self) -> bool:
        """
        Check if required history windows are filled.

        Returns:
            True if all configured history windows are at required depth,
            or if no history is configured.
        """
        config = self._config

        if not config.requires_history:
            return True

        # Check each configured window
        if config.bars_exec_count > 0:
            if len(self._history_bars_exec) < config.bars_exec_count:
                return False

        if config.features_exec_count > 0:
            if len(self._history_features_exec) < config.features_exec_count:
                return False

        if config.features_high_tf_count > 0:
            if len(self._history_features_htf) < config.features_high_tf_count:
                return False

        if config.features_med_tf_count > 0:
            if len(self._history_features_mtf) < config.features_med_tf_count:
                return False

        return True

    def get_tuples(self) -> tuple[tuple, tuple, tuple, tuple]:
        """
        Get immutable history tuples for snapshot.

        Returns:
            Tuple of (bars_exec, features_exec, features_htf, features_mtf)
        """
        return (
            tuple(self._history_bars_exec),
            tuple(self._history_features_exec),
            tuple(self._history_features_htf),
            tuple(self._history_features_mtf),
        )

    def reset(self) -> None:
        """Reset all history windows to empty."""
        self._history_bars_exec = []
        self._history_features_exec = []
        self._history_features_htf = []
        self._history_features_mtf = []
