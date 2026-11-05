"""Plain-value builders for stage tests, so no PDF is needed."""

from xml.etree import ElementTree
from xml.etree.ElementTree import Element

from pdftext.model import BBox, RawChar

DEFAULT_SIZE = 10.0
DEFAULT_ADVANCE = 5.0


def make_char(
    text: str,
    u0: float = 0.0,
    *,
    v: float = 100.0,
    size: float = DEFAULT_SIZE,
    advance: float = DEFAULT_ADVANCE,
    rotation: int = 0,
    seq: int = 0,
) -> RawChar:
    """A char on a horizontal baseline at `v`, whose box spans `u0` to `u0 + advance`."""
    return RawChar(
        bbox=BBox(u0, v - size, u0 + advance, v),
        text=text,
        rotation=rotation,
        size=size,
        u0=u0,
        u1=u0 + advance,
        v=v,
        seq=seq,
    )


def make_chars(
    text: str, u0: float = 0.0, *, v: float = 100.0, first_seq: int = 0, **kwargs: float
) -> tuple[RawChar, ...]:
    """One char per character of `text`, each starting where the last one ends."""
    advance = kwargs.get("advance", DEFAULT_ADVANCE)
    return tuple(
        make_char(char, u0 + index * advance, v=v, seq=first_seq + index, **kwargs)
        for index, char in enumerate(text)
    )


def parse_xml(data: bytes) -> Element:
    """Parse XML the writer produced. Test output only, never untrusted input."""
    return ElementTree.fromstring(data)  # noqa: S314
