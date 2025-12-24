from __future__ import annotations

"""Utility helpers for reading and validating environment configuration.

This module provides a small typed wrapper around os.environ so callers can
safely read configuration values with:

- type conversion (str, int, float, bool)
- default values
- optional validation hooks

The goal is to keep all env access consistent and easy to test.
"""

from dataclasses import dataclass
from typing import Callable, Generic, Optional, TypeVar
import os

T = TypeVar("T")


class EnvVarError(RuntimeError):
    """Raised when an environment variable has an invalid or missing value."""


@dataclass(frozen=True)
class EnvVar(Generic[T]):
    """Descriptor for an environment variable.

    Parameters
    ----------
    name:
        Name of the environment variable.
    cast:
        Callable converting the raw string into the desired type.
    default:
        Optional default value when the env var is not present.
    required:
        When True and no default is provided, raise if the variable is missing.
    validator:
        Optional callable that receives the converted value and raises a
        ValueError if it is not acceptable.
    """

    name: str
    cast: Callable[[str], T]
    default: Optional[T] = None
    required: bool = False
    validator: Optional[Callable[[T], None]] = None

    def read(self) -> T:
        raw = os.getenv(self.name)

        if raw is None:
            if self.default is not None:
                value = self.default
            elif self.required:
                raise EnvVarError(f"Missing required environment variable: {self.name}")
            else:
                # type: ignore[assignment]
                value = None  # allow Optional[T] via type ignore
        else:
            try:
                value = self.cast(raw)
            except Exception as exc:  # noqa: BLE001
                raise EnvVarError(
                    f"Invalid value for environment variable {self.name!r}: {raw!r}"
                ) from exc

        if self.validator is not None and value is not None:
            try:
                self.validator(value)  # type: ignore[arg-type]
            except ValueError as exc:
                raise EnvVarError(
                    f"Validation failed for environment variable {self.name!r}: {exc}"
                ) from exc

        return value  # type: ignore[return-value]


def _to_bool(value: str) -> bool:
    """Convert typical truthy/falsey strings into a bool.

    Accepted true values (case-insensitive): "1", "true", "t", "yes", "y", "on".
    Accepted false values: "0", "false", "f", "no", "n", "off".
    """

    truthy = {"1", "true", "t", "yes", "y", "on"}
    falsey = {"0", "false", "f", "no", "n", "off"}

    lowered = value.strip().lower()
    if lowered in truthy:
        return True
    if lowered in falsey:
        return False
    raise ValueError(f"Cannot interpret {value!r} as a boolean")


# Convenience constructors -------------------------------------------------


def env_str(name: str, *, default: Optional[str] = None, required: bool = False) -> EnvVar[str]:
    """Create a string environment variable descriptor."""

    return EnvVar(name=name, cast=str, default=default, required=required)


def env_int(
    name: str,
    *,
    default: Optional[int] = None,
    required: bool = False,
    min_value: Optional[int] = None,
    max_value: Optional[int] = None,
) -> EnvVar[int]:
    """Create an integer environment variable descriptor with optional bounds."""

    def _validator(value: int) -> None:
        if min_value is not None and value < min_value:
            raise ValueError(f"must be >= {min_value}, got {value}")
        if max_value is not None and value > max_value:
            raise ValueError(f"must be <= {max_value}, got {value}")

    return EnvVar(name=name, cast=int, default=default, required=required, validator=_validator)


def env_float(
    name: str,
    *,
    default: Optional[float] = None,
    required: bool = False,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
) -> EnvVar[float]:
    """Create a float environment variable descriptor with optional bounds."""

    def _validator(value: float) -> None:
        if min_value is not None and value < min_value:
            raise ValueError(f"must be >= {min_value}, got {value}")
        if max_value is not None and value > max_value:
            raise ValueError(f"must be <= {max_value}, got {value}")

    return EnvVar(name=name, cast=float, default=default, required=required, validator=_validator)


def env_bool(
    name: str,
    *,
    default: Optional[bool] = None,
    required: bool = False,
) -> EnvVar[bool]:
    """Create a boolean environment variable descriptor.

    Values are parsed with :func:`_to_bool`.
    """

    return EnvVar(name=name, cast=_to_bool, default=default, required=required)


__all__ = [
    "EnvVarError",
    "EnvVar",
    "env_str",
    "env_int",
    "env_float",
    "env_bool",
]
