"""A spy shared by tests that check PDFium is, or is not, used (SEC-15)."""

from pdftext import adapter


def record_pdfium_calls(monkeypatch):
    """Record each use of PDFium while still letting it run, and return the list of calls."""
    calls = []
    real = adapter.pypdfium2.PdfDocument

    def spy(*args, **kwargs):
        calls.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(adapter.pypdfium2, "PdfDocument", spy)
    return calls
