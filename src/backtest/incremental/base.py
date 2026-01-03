"""
Base class and data structures for incremental structure detectors.

Provides:
- BarData: Immutable bar data passed to structure updates
- BaseIncrementalDetector: Abstract base class for all detectors

All detectors must inherit from BaseIncrementalDetector and implement
the required abstract methods. The base class provides validation
infrastructure with fail-loud errors including actionable fix suggestions.

Performance Contract:
- update(): O(1) or O(log n) depending on detector type
- get_value(): O(1) always
- get_all_values(): O(k) where k = number of output keys

See: docs/architecture/INCREMENTAL_STATE_ARCHITECTURE.md
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class BarData:
    """
    Single bar passed to structure updates.

    Immutable dataclass containing OHLCV data plus any pre-computed
    indicators needed by structure detectors.

    P3-003: The indicators field is stored as MappingProxyType for true
    immutability. Pass a regular dict; it will be wrapped automatically.

    Attributes:
        idx: Bar index (monotonically increasing).
        open: Open price.
        high: High price.
        low: Low price.
        close: Close price.
        volume: Volume.
        indicators: Pre-computed indicator values (immutable view).

    Example:
        >>> bar = BarData(
        ...     idx=100,
        ...     open=50000.0,
        ...     high=50500.0,
        ...     low=49800.0,
        ...     close=50200.0,
        ...     volume=1234.5,
        ...     indicators={"atr": 245.5, "ema_20": 50100.0}
        ... )
        >>> bar.close
        50200.0
        >>> bar.indicators["atr"]
        245.5
    """

    idx: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    # P3-003 FIX: Use Mapping type hint (immutable view)
    indicators: Mapping[str, float]

    def __post_init__(self) -> None:
        """Wrap indicators dict in MappingProxyType for true immutability."""
        # If passed a regular dict, wrap it in MappingProxyType
        if isinstance(self.indicators, dict):
            # Use object.__setattr__ to bypass frozen=True
            object.__setattr__(
                self, "indicators", MappingProxyType(self.indicators)
            )


class BaseIncrementalDetector(ABC):
    """
    Abstract base class for all incremental structure detectors.

    Subclasses must define class attributes and implement abstract methods:

    Class Attributes:
        REQUIRED_PARAMS: List of parameter names that must be provided.
        OPTIONAL_PARAMS: Dict of optional params with their default values.
        DEPENDS_ON: List of dependency types this detector requires.

    Abstract Methods:
        update(bar_idx, bar): Process one bar. Called on TF bar close.
        get_output_keys(): Return list of readable output keys.
        get_value(key): Get output by key. Must be O(1).

    Example:
        @register_structure("my_detector")
        class MyDetector(BaseIncrementalDetector):
            REQUIRED_PARAMS = ["period"]
            OPTIONAL_PARAMS = {"threshold": 0.5}
            DEPENDS_ON = []

            def __init__(self, params: dict, deps: dict):
                self.period = params["period"]
                self.threshold = params.get("threshold", 0.5)
                self._value = 0.0

            def update(self, bar_idx: int, bar: BarData) -> None:
                # Process bar
                self._value = bar.close

            def get_output_keys(self) -> list[str]:
                return ["value"]

            def get_value(self, key: str) -> float:
                if key == "value":
                    return self._value
                raise KeyError(key)
    """

    # Class attributes - subclasses MUST define these
    REQUIRED_PARAMS: list[str] = []
    OPTIONAL_PARAMS: dict[str, Any] = {}
    DEPENDS_ON: list[str] = []

    # Instance attributes set by validate_and_create
    _key: str = ""
    _type: str = ""

    @classmethod
    def validate_and_create(
        cls,
        struct_type: str,
        key: str,
        params: dict[str, Any],
        deps: dict[str, "BaseIncrementalDetector"],
    ) -> "BaseIncrementalDetector":
        """
        Validate parameters and dependencies, then create instance.

        This is the factory method for creating detector instances.
        It performs comprehensive validation before instantiation.

        Args:
            struct_type: The structure type name (for error messages).
            key: The unique key for this structure instance.
            params: Parameter dict from IdeaCard.
            deps: Dict of dependency instances (key = dep type, value = detector).

        Returns:
            Configured detector instance.

        Raises:
            ValueError: If required params are missing or invalid.
            ValueError: If required dependencies are missing.
        """
        # Check required params
        missing_params = [p for p in cls.REQUIRED_PARAMS if p not in params]
        if missing_params:
            param_lines = "\n".join(
                f"      {p}: <value>  # REQUIRED" for p in missing_params
            )
            raise ValueError(
                f"Structure '{key}' (type: {struct_type}) missing required params: {missing_params}\n"
                f"\n"
                f"Fix in IdeaCard:\n"
                f"  - type: {struct_type}\n"
                f"    key: {key}\n"
                f"    params:\n"
                f"{param_lines}"
            )

        # Check dependencies
        missing_deps = [d for d in cls.DEPENDS_ON if d not in deps]
        if missing_deps:
            dep_lines = "\n".join(
                f"      {d}: <key>  # REQUIRED" for d in missing_deps
            )
            raise ValueError(
                f"Structure '{key}' (type: {struct_type}) missing dependencies: {missing_deps}\n"
                f"\n"
                f"Fix in IdeaCard:\n"
                f"  - type: {struct_type}\n"
                f"    key: {key}\n"
                f"    depends_on:\n"
                f"{dep_lines}"
            )

        # Type-specific validation (subclass hook)
        cls._validate_params(struct_type, key, params)

        # Create instance
        instance = cls(params, deps)
        instance._key = key
        instance._type = struct_type

        return instance

    @classmethod
    def _validate_params(
        cls, struct_type: str, key: str, params: dict[str, Any]
    ) -> None:
        """
        Override for type-specific parameter validation.

        Called after checking required/optional params but before instantiation.
        Subclasses should raise ValueError with actionable fix suggestions.

        Args:
            struct_type: The structure type name.
            key: The unique key for this structure instance.
            params: Parameter dict to validate.

        Raises:
            ValueError: If params are invalid.
        """
        pass

    @abstractmethod
    def update(self, bar_idx: int, bar: BarData) -> None:
        """
        Process one bar. Called on TF bar close.

        This method updates internal state based on the new bar data.
        It should be O(1) or O(log n) for performance in the hot loop.

        Args:
            bar_idx: Current bar index.
            bar: Bar data including OHLCV and indicators.
        """
        pass

    @abstractmethod
    def get_output_keys(self) -> list[str]:
        """
        List of readable output keys.

        Returns:
            List of string keys that can be passed to get_value().
        """
        pass

    @abstractmethod
    def get_value(self, key: str) -> float | int | str:
        """
        Get output by key. Must be O(1).

        Args:
            key: Output key name (from get_output_keys()).

        Returns:
            The output value.

        Raises:
            KeyError: If key is not valid.
        """
        pass

    def get_value_safe(self, key: str) -> float | int | str:
        """
        Get output with key validation and helpful error messages.

        This method validates the key exists before calling get_value(),
        providing actionable suggestions if the key is invalid.

        Args:
            key: Output key name.

        Returns:
            The output value.

        Raises:
            KeyError: If key is not valid, with suggestions.
        """
        valid_keys = self.get_output_keys()
        if key not in valid_keys:
            raise KeyError(
                f"Structure '{self._key}' (type: {self._type}) has no output '{key}'\n"
                f"\n"
                f"Available outputs: {valid_keys}\n"
                f"\n"
                f"Fix: Use one of the available output keys above."
            )
        return self.get_value(key)

    def get_all_values(self) -> dict[str, float | int | str]:
        """
        Return all output values as a dictionary.

        Useful for debugging and serialization.

        Returns:
            Dict mapping output keys to their current values.
        """
        return {key: self.get_value(key) for key in self.get_output_keys()}
