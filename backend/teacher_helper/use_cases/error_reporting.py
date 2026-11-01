"""Optional error sink; domain code has no dependency on monitoring providers."""

from collections.abc import Callable
from contextlib import suppress

_reporter: Callable[[Exception], None] | None = None


def set_error_reporter(reporter: Callable[[Exception], None] | None) -> None:
    global _reporter
    _reporter = reporter


def report_error(error: Exception) -> None:
    if _reporter is not None:
        with suppress(Exception):
            _reporter(error)
