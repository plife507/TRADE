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
        {"type": "swing", "key": "pivots", "params": {"left": 5, "right": 5}},
        {"type": "fibonacci", "key": "fib", "uses": "pivots",
         "params": {"levels": [0.382, 0.618]}},
        {"type": "trend", "key": "trend", "uses": "pivots"},
    ]

    state = TFIncrementalState("15m", exec_specs)
    state.update(bar)
    high_level = state.get_value("pivots", "high_level")

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
        ...     {"type": "swing", "key": "pivots", "params": {"left": 5, "right": 5}},
        ...     {"type": "trend", "key": "trend", "uses": "pivots"},
        ... ]
        >>> state = TFIncrementalState("15m", specs)
        >>> state.update(bar)
        >>> state.get_value("pivots", "high_level")
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
        - uses: (optional) Key or list of keys for dependencies

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
            # Parse uses field (can be string or list)
            uses_raw = spec.get("uses", [])
            if isinstance(uses_raw, str):
                uses = [uses_raw]
            else:
                uses = list(uses_raw) if uses_raw else []

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

            # Resolve dependencies from uses list
            deps: dict[str, BaseIncrementalDetector] = {}
            for dep_key in uses:
                if dep_key not in self.structures:
                    available_keys = list(self.structures.keys())
                    available_str = ", ".join(available_keys) if available_keys else "(none defined yet)"
                    raise ValueError(
                        f"Structure '{key}' uses '{dep_key}' which is not yet defined.\n"
                        f"\n"
                        f"Available structures (defined before '{key}'): {available_str}\n"
                        f"\n"
                        f"Fix: Define '{dep_key}' BEFORE '{key}' in the structures list:\n"
                        f"  structures:\n"
                        f"    exec:\n"
                        f"      - type: swing\n"
                        f"        key: {dep_key}\n"
                        f"        ...\n"
                        f"      - type: {struct_type}\n"
                        f"        key: {key}\n"
                        f"        uses: {dep_key}"
                    )
                # Get the dependency's type and add to deps dict keyed by type
                dep_detector = self.structures[dep_key]
                dep_type = dep_detector._type
                deps[dep_type] = dep_detector

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

    def to_json(self) -> dict:
        """Serialize state for crash recovery."""
        data: dict[str, Any] = {
            "timeframe": self.timeframe,
            "bar_idx": self._bar_idx,
            "detectors": {},
        }
        for key, detector in self.structures.items():
            det_state: dict[str, Any] = {
                "type": type(detector).__name__,
                "bar_idx": getattr(detector, '_bar_idx', None),
            }
            # Try to get serializable state from common detector patterns
            if hasattr(detector, 'to_dict'):
                det_state["state"] = detector.to_dict()
            data["detectors"][key] = det_state
        return data

    @classmethod
    def from_json(cls, data: dict) -> TFIncrementalState:
        """Restore state from serialized data. Detectors must be re-registered separately."""
        instance = cls.__new__(cls)
        instance.timeframe = data["timeframe"]
        instance._bar_idx = data.get("bar_idx", 0)
        instance.structures = {}  # Detectors must be re-registered
        instance._update_order = []
        return instance

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

    Manages an exec_tf (execution) timeframe state plus optional med_tf and
    high_tf timeframe states. Provides path-based access to structure values.

    Path Format:
        - "exec.<struct_key>.<output_key>" - Exec TF structure value
        - "med_tf_<tf>.<struct_key>.<output_key>" - Med TF structure value
        - "high_tf_<tf>.<struct_key>.<output_key>" - High TF structure value

    Example:
        >>> multi = MultiTFIncrementalState(
        ...     exec_tf="15m",
        ...     exec_specs=[{"type": "swing", "key": "swing", "params": {...}}],
        ...     med_tf_configs={"4h": [{"type": "swing", "key": "swing_4h", "params": {...}}]},
        ...     high_tf_configs={"D": [{"type": "swing", "key": "swing_d", "params": {...}}]},
        ... )
        >>> multi.update_exec(bar_15m)
        >>> multi.update_med_tf("4h", bar_4h)
        >>> multi.update_high_tf("D", bar_d)
        >>> multi.get_value("exec.swing.high_level")
        50000.0
        >>> multi.get_value("med_tf_4h.swing_4h.high_level")
        50200.0
        >>> multi.get_value("high_tf_D.swing_d.high_level")
        50500.0

    Attributes:
        exec_tf: The execution timeframe identifier.
        exec: TFIncrementalState for the exec timeframe.
        med_tf: Dict mapping med_tf names to TFIncrementalState instances.
        high_tf: Dict mapping high_tf names to TFIncrementalState instances.
    """

    def __init__(
        self,
        exec_tf: str,
        exec_specs: list[dict[str, Any]],
        med_tf_configs: dict[str, list[dict[str, Any]]] | None = None,
        high_tf_configs: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        """
        Initialize multi-TF state container.

        Args:
            exec_tf: The execution timeframe identifier (e.g., "15m").
            exec_specs: List of structure specs for the exec timeframe.
            med_tf_configs: Dict mapping med_tf names to their structure specs.
                         Keys are timeframe names (e.g., "4h").
            high_tf_configs: Dict mapping high_tf names to their structure specs.
                         Keys are timeframe names (e.g., "D", "12h").

        Raises:
            ValueError: If any structure spec is invalid.
        """
        self.exec_tf = exec_tf
        self.exec = TFIncrementalState(exec_tf, exec_specs)

        self.med_tf: dict[str, TFIncrementalState] = {}
        if med_tf_configs:
            for tf, specs in med_tf_configs.items():
                self.med_tf[tf] = TFIncrementalState(tf, specs)

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

    def update_med_tf(self, timeframe: str, bar: "BarData") -> None:
        """
        Update med_tf structures with new bar.

        Called only when a med_tf bar closes.

        Args:
            timeframe: The med_tf name (must match a key in med_tf_configs).
            bar: Bar data for the med_tf.

        Raises:
            KeyError: If timeframe not configured.
            ValueError: If bar index doesn't increase.
        """
        if timeframe not in self.med_tf:
            available = list(self.med_tf.keys())
            available_str = ", ".join(available) if available else "(none configured)"
            raise KeyError(
                f"Med TF '{timeframe}' not configured.\n"
                f"\n"
                f"Available med_tfs: {available_str}\n"
                f"\n"
                f"Fix: Add med_tf configuration to your Play:\n"
                f"  structures:\n"
                f"    med_tf:\n"
                f"      \"{timeframe}\":\n"
                f"        - type: swing\n"
                f"          key: swing_{timeframe}\n"
                f"          params:\n"
                f"            left: 3\n"
                f"            right: 3"
            )
        self.med_tf[timeframe].update(bar)

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
            - "med_tf_<tf>.<struct_key>.<output_key>" for med_tf
            - "high_tf_<tf>.<struct_key>.<output_key>" for high_tf

        Examples:
            - "exec.swing.high_level" - Swing high from exec_tf
            - "med_tf_4h.trend_4h.direction" - Trend direction from 4h med_tf
            - "high_tf_D.trend_d.direction" - Trend direction from D high_tf
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
                f"  - med_tf_4h.trend_4h.direction\n"
                f"  - high_tf_D.trend_d.direction"
            )

        tf_role = parts[0]
        struct_key = parts[1]
        # Join remaining parts for output key (handles keys like "level_0.618")
        output_key = ".".join(parts[2:])

        if tf_role == "exec":
            return self.exec.get_value(struct_key, output_key)

        elif tf_role.startswith("med_tf_"):
            tf_name = tf_role[7:]  # Strip "med_tf_" prefix

            if tf_name not in self.med_tf:
                available = list(self.med_tf.keys())
                available_str = ", ".join(available) if available else "(none configured)"

                suggestions = [f"  - exec.{struct_key}.{output_key}"]
                for med_tf_name in available:
                    suggestions.append(f"  - med_tf_{med_tf_name}.{struct_key}.{output_key}")

                raise KeyError(
                    f"Med TF '{tf_name}' not configured.\n"
                    f"\n"
                    f"Available med_tfs: {available_str}\n"
                    f"\n"
                    f"Valid paths might be:\n"
                    + "\n".join(suggestions)
                )

            return self.med_tf[tf_name].get_value(struct_key, output_key)

        elif tf_role.startswith("high_tf_"):
            tf_name = tf_role[8:]  # Strip "high_tf_" prefix

            if tf_name not in self.high_tf:
                available = list(self.high_tf.keys())
                available_str = ", ".join(available) if available else "(none configured)"

                suggestions = [f"  - exec.{struct_key}.{output_key}"]
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
            available_med_tfs = list(self.med_tf.keys())
            available_high_tfs = list(self.high_tf.keys())
            valid_prefixes = (
                ["exec"]
                + [f"med_tf_{tf}" for tf in available_med_tfs]
                + [f"high_tf_{tf}" for tf in available_high_tfs]
            )
            prefixes_str = ", ".join(valid_prefixes) if valid_prefixes else "exec"

            raise ValueError(
                f"Invalid tf_role in path: '{tf_role}'\n"
                f"\n"
                f"Path must start with 'exec', 'med_tf_<tf>', or 'high_tf_<tf>'.\n"
                f"\n"
                f"Valid prefixes for this configuration: {prefixes_str}\n"
                f"\n"
                f"Examples:\n"
                f"  - exec.swing.high_level\n"
                + ("\n".join(f"  - med_tf_{tf}.swing.high_level" for tf in available_med_tfs) + "\n" if available_med_tfs else "")
                + ("\n".join(f"  - high_tf_{tf}.swing.high_level" for tf in available_high_tfs) if available_high_tfs else "")
            )

    def list_med_tfs(self) -> list[str]:
        """Return list of configured med_tf names."""
        return list(self.med_tf.keys())

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

        # Med TF paths
        for tf_name, tf_state in self.med_tf.items():
            for struct_key in tf_state.list_structures():
                for output_key in tf_state.list_outputs(struct_key):
                    paths.append(f"med_tf_{tf_name}.{struct_key}.{output_key}")

        # High TF paths
        for tf_name, tf_state in self.high_tf.items():
            for struct_key in tf_state.list_structures():
                for output_key in tf_state.list_outputs(struct_key):
                    paths.append(f"high_tf_{tf_name}.{struct_key}.{output_key}")

        return paths

    def to_json(self) -> dict:
        """Serialize all timeframe states for crash recovery."""
        return {
            "exec_tf": self.exec_tf,
            "exec": self.exec.to_json(),
            "med_tf": {
                tf: state.to_json() for tf, state in self.med_tf.items()
            },
            "high_tf": {
                tf: state.to_json() for tf, state in self.high_tf.items()
            },
        }

    @classmethod
    def from_json(cls, data: dict) -> MultiTFIncrementalState:
        """Restore multi-TF state from serialized data."""
        instance = cls.__new__(cls)
        instance.exec_tf = data["exec_tf"]
        instance.exec = TFIncrementalState.from_json(data["exec"])
        instance.med_tf = {
            tf: TFIncrementalState.from_json(tf_data)
            for tf, tf_data in data.get("med_tf", {}).items()
        }
        instance.high_tf = {
            tf: TFIncrementalState.from_json(tf_data)
            for tf, tf_data in data.get("high_tf", {}).items()
        }
        return instance

    def reset(self) -> None:
        """Reset all TF states for new backtest run."""
        self.exec.reset()
        for tf_state in self.med_tf.values():
            tf_state.reset()
        for tf_state in self.high_tf.values():
            tf_state.reset()

    def __repr__(self) -> str:
        """Return string representation."""
        med_tf_names = ", ".join(self.med_tf.keys()) if self.med_tf else "(none)"
        high_tf_names = ", ".join(self.high_tf.keys()) if self.high_tf else "(none)"
        return (
            f"MultiTFIncrementalState("
            f"exec_tf={self.exec_tf!r}, "
            f"med_tfs=[{med_tf_names}], "
            f"high_tfs=[{high_tf_names}])"
        )
