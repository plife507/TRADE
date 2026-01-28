"""
History management module for backtest execution.

This module handles rolling history window management:
- HistoryManager: Class to manage history state and operations
- parse_history_config_impl: Parse HistoryConfig from SystemConfig
- update_history_impl: Update rolling history windows
- is_history_ready_impl: Check if history windows are filled
- get_history_tuples_impl: Get immutable history tuples for snapshot

Used by BacktestRunner for tracking bar history during execution.
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
    history data. Used by BacktestRunner to track bar and feature history.
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
        self._history_features_high_tf: list[FeatureSnapshot] = []
        self._history_features_med_tf: list[FeatureSnapshot] = []

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
    def features_high_tf(self) -> list[FeatureSnapshot]:
        """Get current high_tf feature history."""
        return self._history_features_high_tf

    @property
    def features_med_tf(self) -> list[FeatureSnapshot]:
        """Get current med_tf feature history."""
        return self._history_features_med_tf

    def update(
        self,
        bar: CanonicalBar,
        features_exec: FeatureSnapshot,
        high_tf_updated: bool,
        med_tf_updated: bool,
        features_high_tf: FeatureSnapshot | None,
        features_med_tf: FeatureSnapshot | None,
    ) -> None:
        """
        Update rolling history windows.

        Called after each bar close, before snapshot build.
        Maintains bounded windows per HistoryConfig.

        Args:
            bar: Current exec-TF bar
            features_exec: Current exec-TF features
            high_tf_updated: Whether high_tf cache was updated this step
            med_tf_updated: Whether med_tf cache was updated this step
            features_high_tf: Current high_tf features (if updated)
            features_med_tf: Current med_tf features (if updated)
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

        # Update high_tf feature history (only on high_tf close)
        if config.features_high_tf_count > 0 and high_tf_updated and features_high_tf and features_high_tf.ready:
            self._history_features_high_tf.append(features_high_tf)
            if len(self._history_features_high_tf) > config.features_high_tf_count:
                self._history_features_high_tf = self._history_features_high_tf[-config.features_high_tf_count:]

        # Update med_tf feature history (only on med_tf close)
        if config.features_med_tf_count > 0 and med_tf_updated and features_med_tf and features_med_tf.ready:
            self._history_features_med_tf.append(features_med_tf)
            if len(self._history_features_med_tf) > config.features_med_tf_count:
                self._history_features_med_tf = self._history_features_med_tf[-config.features_med_tf_count:]

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
            if len(self._history_features_high_tf) < config.features_high_tf_count:
                return False

        if config.features_med_tf_count > 0:
            if len(self._history_features_med_tf) < config.features_med_tf_count:
                return False

        return True

    def get_tuples(self) -> tuple[tuple, tuple, tuple, tuple]:
        """
        Get immutable history tuples for snapshot.

        Returns:
            Tuple of (bars_exec, features_exec, features_high_tf, features_med_tf)
        """
        return (
            tuple(self._history_bars_exec),
            tuple(self._history_features_exec),
            tuple(self._history_features_high_tf),
            tuple(self._history_features_med_tf),
        )

    def reset(self) -> None:
        """Reset all history windows to empty."""
        self._history_bars_exec = []
        self._history_features_exec = []
        self._history_features_high_tf = []
        self._history_features_med_tf = []
