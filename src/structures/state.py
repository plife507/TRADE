"""
Incremental state containers for single and multi-timeframe structure management.

Provides:
- TFIncrementalState: Container for all structures on a single timeframe
- MultiTFIncrementalState: Unified container for exec + high_tf states

These containers manage structure creation, dependency resolution, and
bar-by-bar updates. All errors include actionable fix suggestions.

Example:
    # Create exec_tf state with swing -> fib -> trend chain
    exec_specs = [
        {"type": "swing", "key": "swing", "params": {"left": 5, "right": 5}},
        {"type": "fibonacci", "key": "fib", "depends_on": {"swing": "swing"},
         "params": {"levels": [0.382, 0.618]}},
        {"type": "trend", "key": "trend", "depends_on": {"swing": "swing"}},
    ]

    state = TFIncrementalState("15m", exec_specs)
    state.update(bar)
    high_level = state.get_value("swing", "high_level")

See: docs/architecture/INCREMENTAL_STATE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import BaseIncrementalDetector
from .registry import STRUCTURE_REGISTRY

if TYPE_CHECKING:
    from .base import BarData


class TFIncrementalState:
    """
    Incremental state for a single timeframe.

    Manages a collection of structure detectors for one timeframe (e.g., 15m).
    Structures are built from specs in the order provided, with dependencies
    resolved automatically.

    Structure specs are validated at construction time:
    - Type must be registered in STRUCTURE_REGISTRY
    - Required params must be provided
    - Dependencies must be defined earlier in the spec list

    Attributes:
        timeframe: The timeframe identifier (e.g., "15m", "1h").
        structures: Dict mapping structure keys to detector instances.

    Example:
        >>> specs = [
        ...     {"type": "swing", "key": "swing", "params": {"left": 5, "right": 5}},
        ...     {"type": "trend", "key": "trend", "depends_on": {"swing": "swing"}},
        ... ]
        >>> state = TFIncrementalState("15m", specs)
        >>> state.update(bar)
        >>> state.get_value("swing", "high_level")
        50000.0
    """

    def __init__(self, timeframe: str, structure_specs: list[dict[str, Any]]) -> None:
        """
        Initialize TF state from structure specs.

        Builds structures from specs in order, resolving dependencies.
        Each spec must contain:
        - type: Registered structure type name
        - key: Unique identifier for this instance
        - params: (optional) Dict of parameters
        - depends_on: (optional) Dict mapping dep type to key

        Args:
            timeframe: The timeframe identifier.
            structure_specs: List of structure specifications.

        Raises:
            ValueError: If type is not registered, params invalid, or deps missing.
        """
        self.timeframe = timeframe
        self._bar_idx: int = -1
        self.structures: dict[str, BaseIncrementalDetector] = {}
        self._update_order: list[str] = []

        self._build_structures(structure_specs)

    def _build_structures(self, specs: list[dict[str, Any]]) -> None:
        """
        Build structure detectors from specs.

        Processes specs in order, resolving dependencies from previously
        built structures. Attaches _key and _type to each detector for
        error messages.

        Args:
            specs: List of structure specifications.

        Raises:
            ValueError: If type not registered, params invalid, or deps missing.
        """
        for spec in specs:
            struct_type = spec.get("type")
            key = spec.get("key")
            params = spec.get("params", {})
            depends_on = spec.get("depends_on", {})

            # Validate required fields
            if not struct_type:
                raise ValueError(
                    f"Structure spec missing 'type' field.\n"
                    f"\n"
                    f"Fix: Add 'type' to the structure spec:\n"
                    f"  - type: swing\n"
                    f"    key: <unique_key>"
                )

            if not key:
                raise ValueError(
                    f"Structure spec for type '{struct_type}' missing 'key' field.\n"
                    f"\n"
                    f"Fix: Add 'key' to the structure spec:\n"
                    f"  - type: {struct_type}\n"
                    f"    key: <unique_key>"
                )

            # Check for duplicate keys
            if key in self.structures:
                raise ValueError(
                    f"Duplicate structure key '{key}' in timeframe '{self.timeframe}'.\n"
                    f"\n"
                    f"Fix: Use unique keys for each structure."
                )

            # Validate type is registered
            if struct_type not in STRUCTURE_REGISTRY:
                available = list(STRUCTURE_REGISTRY.keys())
                available_str = ", ".join(available) if available else "(none registered)"
                raise ValueError(
                    f"Unknown structure type: '{struct_type}'\n"
                    f"\n"
                    f"Available types: {available_str}\n"
                    f"\n"
                    f"Fix: Use one of the available types, or register a new detector."
                )

            cls = STRUCTURE_REGISTRY[struct_type]

            # Resolve dependencies
            deps: dict[str, BaseIncrementalDetector] = {}
            for dep_type, dep_key in depends_on.items():
                if dep_key not in self.structures:
                    available_keys = list(self.structures.keys())
                    available_str = ", ".join(available_keys) if available_keys else "(none defined yet)"
                    raise ValueError(
                        f"Structure '{key}' depends on '{dep_key}' which is not yet defined.\n"
                        f"\n"
                        f"Available structures (defined before '{key}'): {available_str}\n"
                        f"\n"
                        f"Fix: Define '{dep_key}' BEFORE '{key}' in the structures list:\n"
                        f"  structures:\n"
                        f"    exec:\n"
                        f"      - type: <dep_type>  # Define dependency first\n"
                        f"        key: {dep_key}\n"
                        f"        ...\n"
                        f"      - type: {struct_type}  # Then the dependent structure\n"
                        f"        key: {key}\n"
                        f"        depends_on:\n"
                        f"          {dep_type}: {dep_key}"
                    )
                deps[dep_type] = self.structures[dep_key]

            # Create detector instance with validation
            detector = cls.validate_and_create(struct_type, key, params, deps)

            self.structures[key] = detector
            self._update_order.append(key)

    def update(self, bar: "BarData") -> None:
        """
        Update all structures with new bar data.

        Structures are updated in the order they were defined (dependency order).
        Bar index must be monotonically increasing.

        Args:
            bar: Bar data containing OHLCV and indicators.

        Raises:
            ValueError: If bar.idx is not greater than the last processed index.
        """
        if bar.idx <= self._bar_idx:
            raise ValueError(
                f"Bar index must increase monotonically. "
                f"Got bar.idx={bar.idx}, but last processed was {self._bar_idx}.\n"
                f"\n"
                f"Fix: Ensure bars are processed in chronological order."
            )
        self._bar_idx = bar.idx

        for key in self._update_order:
            self.structures[key].update(bar.idx, bar)

    def get_value(self, struct_key: str, output_key: str) -> float | int | str:
        """
        Get a structure output value.

        Args:
            struct_key: The structure key (from spec).
            output_key: The output key (from detector.get_output_keys()).

        Returns:
            The output value.

        Raises:
            KeyError: If struct_key not found or output_key invalid.
        """
        if struct_key not in self.structures:
            available = list(self.structures.keys())
            available_str = ", ".join(available) if available else "(none defined)"
            raise KeyError(
                f"Structure '{struct_key}' not defined for timeframe '{self.timeframe}'.\n"
                f"\n"
                f"Available structures: {available_str}\n"
                f"\n"
                f"Fix: Use one of the available structure keys, or add the structure to your Play."
            )

        return self.structures[struct_key].get_value_safe(output_key)

    def list_structures(self) -> list[str]:
        """Return list of structure keys in update order."""
        return list(self._update_order)

    def list_outputs(self, struct_key: str) -> list[str]:
        """
        Return list of output keys for a structure.

        Args:
            struct_key: The structure key.

        Returns:
            List of output key names.

        Raises:
            KeyError: If struct_key not found.
        """
        if struct_key not in self.structures:
            available = list(self.structures.keys())
            raise KeyError(
                f"Structure '{struct_key}' not defined.\n"
                f"Available: {available}"
            )
        return self.structures[struct_key].get_output_keys()

    def reset(self) -> None:
        """Reset state for new backtest run."""
        self._bar_idx = -1
        for struct in self.structures.values():
            if hasattr(struct, 'reset'):
                struct.reset()

    def __repr__(self) -> str:
        """Return string representation."""
        struct_keys = ", ".join(self._update_order)
        return f"TFIncrementalState(timeframe={self.timeframe!r}, structures=[{struct_keys}])"


class MultiTFIncrementalState:
    """
    Unified container for all timeframe states.

    Manages an exec_tf (execution) timeframe state plus optional high_tf (structure)
    timeframe states. Provides path-based access to structure values.

    Path Format:
        - "exec.<struct_key>.<output_key>" - Exec TF structure value
        - "high_tf_<tf>.<struct_key>.<output_key>" - High TF structure value

    Example:
        >>> multi = MultiTFIncrementalState(
        ...     exec_tf="15m",
        ...     exec_specs=[{"type": "swing", "key": "swing", "params": {...}}],
        ...     high_tf_configs={"1h": [{"type": "swing", "key": "swing_1h", "params": {...}}]}
        ... )
        >>> multi.update_exec(bar_15m)
        >>> multi.update_high_tf("1h", bar_1h)
        >>> multi.get_value("exec.swing.high_level")
        50000.0
        >>> multi.get_value("high_tf_1h.swing_1h.high_level")
        50500.0

    Attributes:
        exec_tf: The execution timeframe identifier.
        exec: TFIncrementalState for the exec timeframe.
        high_tf: Dict mapping high_tf names to TFIncrementalState instances.
    """

    def __init__(
        self,
        exec_tf: str,
        exec_specs: list[dict[str, Any]],
        high_tf_configs: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        """
        Initialize multi-TF state container.

        Args:
            exec_tf: The execution timeframe identifier (e.g., "15m").
            exec_specs: List of structure specs for the exec timeframe.
            high_tf_configs: Dict mapping high_tf names to their structure specs.
                         Keys are timeframe names (e.g., "1h", "4h").

        Raises:
            ValueError: If any structure spec is invalid.
        """
        self.exec_tf = exec_tf
        self.exec = TFIncrementalState(exec_tf, exec_specs)

        self.high_tf: dict[str, TFIncrementalState] = {}
        if high_tf_configs:
            for tf, specs in high_tf_configs.items():
                self.high_tf[tf] = TFIncrementalState(tf, specs)

    def update_exec(self, bar: "BarData") -> None:
        """
        Update exec TF structures with new bar.

        Called every exec bar.

        Args:
            bar: Bar data for the exec timeframe.

        Raises:
            ValueError: If bar index doesn't increase.
        """
        self.exec.update(bar)

    def update_high_tf(self, timeframe: str, bar: "BarData") -> None:
        """
        Update high_tf structures with new bar.

        Called only when a high_tf bar closes.

        Args:
            timeframe: The high_tf name (must match a key in high_tf_configs).
            bar: Bar data for the high_tf.

        Raises:
            KeyError: If timeframe not configured.
            ValueError: If bar index doesn't increase.
        """
        if timeframe not in self.high_tf:
            available = list(self.high_tf.keys())
            available_str = ", ".join(available) if available else "(none configured)"
            raise KeyError(
                f"High TF '{timeframe}' not configured.\n"
                f"\n"
                f"Available high_tfs: {available_str}\n"
                f"\n"
                f"Fix: Add high_tf configuration to your Play:\n"
                f"  structures:\n"
                f"    high_tf:\n"
                f"      \"{timeframe}\":\n"
                f"        - type: swing\n"
                f"          key: swing_{timeframe.replace('h', 'H')}\n"
                f"          params:\n"
                f"            left: 3\n"
                f"            right: 3"
            )
        self.high_tf[timeframe].update(bar)

    def get_value(self, path: str) -> float | int | str:
        """
        Get structure value by path.

        Path format:
            - "exec.<struct_key>.<output_key>" for exec_tf
            - "high_tf_<tf>.<struct_key>.<output_key>" for high_tf

        Examples:
            - "exec.swing.high_level" - Swing high from exec_tf
            - "high_tf_1h.trend.direction" - Trend direction from 1h high_tf
            - "high_tf_4h.fib.level_0.618" - Fib level from 4h high_tf

        Args:
            path: Dot-separated path to the value.

        Returns:
            The output value.

        Raises:
            ValueError: If path format is invalid.
            KeyError: If timeframe, structure, or output not found.
        """
        parts = path.split(".")

        if len(parts) < 3:
            raise ValueError(
                f"Invalid path: '{path}'\n"
                f"\n"
                f"Path must have at least 3 parts: <tf_role>.<struct_key>.<output_key>\n"
                f"\n"
                f"Examples:\n"
                f"  - exec.swing.high_level\n"
                f"  - high_tf_1h.trend.direction\n"
                f"  - high_tf_4h.fib.level_0.618"
            )

        tf_role = parts[0]
        struct_key = parts[1]
        # Join remaining parts for output key (handles keys like "level_0.618")
        output_key = ".".join(parts[2:])

        if tf_role == "exec":
            return self.exec.get_value(struct_key, output_key)

        elif tf_role.startswith("high_tf_"):
            tf_name = tf_role[8:]  # Strip "high_tf_" prefix

            if tf_name not in self.high_tf:
                available = list(self.high_tf.keys())
                available_str = ", ".join(available) if available else "(none configured)"

                # Provide suggestions
                suggestions = []
                suggestions.append(f"  - exec.{struct_key}.{output_key}")
                for high_tf_name in available:
                    suggestions.append(f"  - high_tf_{high_tf_name}.{struct_key}.{output_key}")

                raise KeyError(
                    f"High TF '{tf_name}' not configured.\n"
                    f"\n"
                    f"Available high_tfs: {available_str}\n"
                    f"\n"
                    f"Valid paths might be:\n"
                    + "\n".join(suggestions)
                )

            return self.high_tf[tf_name].get_value(struct_key, output_key)

        else:
            # Provide helpful suggestions
            available_high_tfs = list(self.high_tf.keys())
            valid_prefixes = ["exec"] + [f"high_tf_{tf}" for tf in available_high_tfs]
            prefixes_str = ", ".join(valid_prefixes) if valid_prefixes else "exec"

            raise ValueError(
                f"Invalid tf_role in path: '{tf_role}'\n"
                f"\n"
                f"Path must start with 'exec' or 'high_tf_<tf>'.\n"
                f"\n"
                f"Valid prefixes for this configuration: {prefixes_str}\n"
                f"\n"
                f"Examples:\n"
                f"  - exec.swing.high_level\n"
                + ("\n".join(f"  - high_tf_{tf}.swing.high_level" for tf in available_high_tfs) if available_high_tfs else "")
            )

    def list_high_tfs(self) -> list[str]:
        """Return list of configured high_tf names."""
        return list(self.high_tf.keys())

    def list_all_paths(self) -> list[str]:
        """
        Return list of all valid paths.

        Useful for debugging and discovery.

        Returns:
            List of all valid "tf.struct.output" paths.
        """
        paths: list[str] = []

        # Exec paths
        for struct_key in self.exec.list_structures():
            for output_key in self.exec.list_outputs(struct_key):
                paths.append(f"exec.{struct_key}.{output_key}")

        # High TF paths
        for tf_name, tf_state in self.high_tf.items():
            for struct_key in tf_state.list_structures():
                for output_key in tf_state.list_outputs(struct_key):
                    paths.append(f"high_tf_{tf_name}.{struct_key}.{output_key}")

        return paths

    def reset(self) -> None:
        """Reset all TF states for new backtest run."""
        self.exec.reset()
        for tf_state in self.high_tf.values():
            tf_state.reset()

    def __repr__(self) -> str:
        """Return string representation."""
        high_tf_names = ", ".join(self.high_tf.keys()) if self.high_tf else "(none)"
        return (
            f"MultiTFIncrementalState("
            f"exec_tf={self.exec_tf!r}, "
            f"high_tfs=[{high_tf_names}])"
        )
