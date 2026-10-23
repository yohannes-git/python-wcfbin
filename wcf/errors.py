"""The exception of the library."""

from contextlib import contextmanager

__all__ = ['WcfBinaryError', 'binary_errors']


class WcfBinaryError(ValueError):
    """Malformed, unsupported, over-quota or unrepresentable MC-NBFX,
    MC-NBFS or MC-NBFSE data, or XML that cannot be converted.

    Every error on input data is a WcfBinaryError (a ValueError);
    TypeError is kept for wrong uses of the API.
    """


@contextmanager
def binary_errors():
    """Report the ValueErrors of the standard library (UnicodeDecodeError,
    binascii.Error, ...) raised on input data as WcfBinaryError."""
    try:
        yield
    except WcfBinaryError:
        raise
    except ValueError as error:
        raise WcfBinaryError(str(error)) from error
