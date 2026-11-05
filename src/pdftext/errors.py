"""Public exceptions. Every message is safe to print: it never holds PDF text or paths."""


class PdftextError(Exception):
    """Base class for errors that end a conversion."""


class InvalidPdfError(PdftextError):
    """The input is not a readable PDF, or its path can't be read."""


class EncryptedPdfError(PdftextError):
    """The input needs a password."""


class LimitExceededError(PdftextError):
    """The input exceeds a configured limit."""
