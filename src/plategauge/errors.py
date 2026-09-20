"""Project-specific exception types."""


class PlateGaugeError(Exception):
    """Base exception for expected PlateGauge failures."""


class DataIntegrityError(PlateGaugeError, ValueError):
    """Raised when dataset or manifest invariants do not hold."""


class OptionalDependencyError(PlateGaugeError, ImportError):
    """Raised when an explicitly requested optional feature is unavailable."""


def missing_extra(feature: str, extra: str, package: str) -> OptionalDependencyError:
    """Return an actionable dependency error without importing packaging tools."""

    return OptionalDependencyError(
        f"{feature} requires optional package '{package}'. "
        f"Install PlateGauge with the '{extra}' extra."
    )
