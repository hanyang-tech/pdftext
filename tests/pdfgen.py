"""A small hand-written PDF generator, so tests control exactly what a page holds.

Text is drawn with one simple font whose `/ToUnicode` map assigns every distinct
character in the document its own single-byte code. Any Unicode text, including
characters XML forbids, can therefore appear in a PDF that pdfminer reads back as given.
Coordinates are PDF user space: points, origin at the bottom left.
"""

import hashlib
import struct
from dataclasses import dataclass
from itertools import count

GLYPH_WIDTH = 600  # every code is 0.6 em wide, so advances are easy to predict
MAX_DISTINCT_CHARS = 255


@dataclass(frozen=True)
class TextItem:
    x: float
    y: float
    text: str
    size: float = 12.0


@dataclass(frozen=True)
class PageSpec:
    texts: tuple[TextItem, ...] = ()
    mediabox: tuple[float, float, float, float] = (0, 0, 612, 792)
    rotate: int = 0
    transform: tuple[float, float, float, float, float, float] | None = None  # a `cm` for the text


def page_object_id(index: int) -> int:
    """The object number of page `index` (from 0) in a PDF made by `build_objects`."""
    return 5 + 2 * index


def build_pdf(pages: list[PageSpec]) -> bytes:
    """Return the bytes of a PDF with one page per spec."""
    return serialise(build_objects(pages))


def build_objects(pages: list[PageSpec]) -> dict[int, bytes]:
    """The numbered objects of `build_pdf`, so a test can damage one before `serialise`.

    Object 2 is the page tree and object `page_object_id(index)` is page `index`, followed by its
    content stream. Objects 1 to 4 are the catalog, the tree, the font and its ToUnicode map.
    """
    codes = _assign_codes(pages)
    page_ids = [page_object_id(index) for index in range(len(pages))]
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: _pages_object(page_ids),
        3: _font_object(),
        4: _stream(_to_unicode_cmap(codes)),
    }
    for page_id, page in zip(page_ids, pages, strict=True):
        objects[page_id] = _page_object(page, page_id + 1)
        objects[page_id + 1] = _stream(_content(page, codes))
    return objects


def dense_pages(
    page_count: int, lines_per_page: int = 40, words_per_line: int = 10
) -> list[PageSpec]:
    """Pages full of distinct short words, for tests that need many pages of real text."""
    return [
        PageSpec(
            tuple(
                TextItem(
                    x=50,
                    y=760 - 18 * line,
                    text=" ".join(f"p{page}l{line}w{word}" for word in range(words_per_line)),
                    size=9,
                )
                for line in range(lines_per_page)
            )
        )
        for page in range(page_count)
    ]


def numbered_pages(count: int) -> list[PageSpec]:
    """Pages that each hold one word, `PAGE1`, `PAGE2` and so on, so a wrong page shows."""
    return [PageSpec((TextItem(50, 700, f"PAGE{number}"),)) for number in range(1, count + 1)]


def _assign_codes(pages: list[PageSpec]) -> dict[str, int]:
    codes: dict[str, int] = {}
    next_code = count(1)
    for page in pages:
        for item in page.texts:
            for char in item.text:
                if char not in codes:
                    codes[char] = next(next_code)
    if len(codes) > MAX_DISTINCT_CHARS:
        raise ValueError(f"{len(codes)} distinct characters, at most {MAX_DISTINCT_CHARS} fit")
    return codes


def _pages_object(page_ids: list[int]) -> bytes:
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    return f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode()


def _font_object() -> bytes:
    widths = " ".join([str(GLYPH_WIDTH)] * 256)
    return (
        "<< /Type /Font /Subtype /Type1 /BaseFont /TestMono /FirstChar 0 /LastChar 255 "
        f"/Widths [{widths}] /ToUnicode 4 0 R /FontDescriptor << /Type /FontDescriptor "
        "/FontName /TestMono /Flags 32 /FontBBox [0 -200 600 800] /ItalicAngle 0 "
        "/Ascent 800 /Descent -200 /CapHeight 700 /StemV 80 >> >>"
    ).encode()


def _to_unicode_cmap(codes: dict[str, int]) -> bytes:
    entries = "\n".join(
        f"<{code:02X}> <{char.encode('utf-16-be', 'surrogatepass').hex().upper()}>"
        for char, code in codes.items()
    )
    return (
        "/CIDInit /ProcSet findresource begin 12 dict begin begincmap\n"
        "/CMapName /Adobe-Identity-UCS def /CMapType 2 def\n"
        "1 begincodespacerange <00> <FF> endcodespacerange\n"
        f"{len(codes)} beginbfchar\n{entries}\nendbfchar\n"
        "endcmap CMapName currentdict /CMap defineresource pop end end"
    ).encode("ascii")


def _page_object(page: PageSpec, content_id: int) -> bytes:
    box = " ".join(f"{value:g}" for value in page.mediabox)
    return (
        f"<< /Type /Page /Parent 2 0 R /MediaBox [{box}] /Rotate {page.rotate} "
        f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
    ).encode()


def _content(page: PageSpec, codes: dict[str, int]) -> bytes:
    operations = [
        f"BT /F1 {item.size:g} Tf {item.x:g} {item.y:g} Td "
        f"<{''.join(f'{codes[char]:02X}' for char in item.text)}> Tj ET"
        for item in page.texts
    ]
    if page.transform is not None:
        # Fixed-point, because PDF has no exponent notation, so a huge value is written in full.
        matrix = " ".join(f"{value:f}" for value in page.transform)
        operations = [f"q {matrix} cm", *operations, "Q"]
    return "\n".join(operations).encode("ascii")


def _stream(data: bytes) -> bytes:
    return b"<< /Length %d >>\nstream\n" % len(data) + data + b"\nendstream"


def serialise(objects: dict[int, bytes], trailer_extra: str = "") -> bytes:
    """Write numbered object bodies as a PDF. Object 1 must be the catalog."""
    out = bytearray(b"%PDF-1.7\n")
    offsets: dict[int, int] = {}
    for number, body in objects.items():
        offsets[number] = len(out)
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref_offset = len(out)
    size = max(objects) + 1
    out += b"xref\n0 %d\n0000000000 65535 f \n" % size
    for number in range(1, size):
        out += b"%010d 00000 n \n" % offsets[number]
    trailer = f"<< /Size {size} /Root 1 0 R {trailer_extra} >>".encode("ascii")
    out += b"trailer\n" + trailer + b"\nstartxref\n%d\n%%%%EOF\n" % xref_offset
    return bytes(out)


def build_image_pdf(
    image: tuple[float, float, float, float],
    mediabox: tuple[float, float, float, float] = (0, 0, 612, 792),
) -> bytes:
    """A one-page PDF holding only a grey image, drawn at `image` as (x, y, width, height).

    Numbers are written in fixed point, because PDF has no exponent notation.
    """
    x, y, width, height = image
    box = " ".join(f"{value:g}" for value in mediabox)
    objects = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [{box}] "
            "/Resources << /XObject << /Im 4 0 R >> >> /Contents 5 0 R >>"
        ).encode(),
        4: (
            b"<< /Type /XObject /Subtype /Image /Width 1 /Height 1 "
            b"/ColorSpace /DeviceGray /BitsPerComponent 8 /Length 1 >>\nstream\n\x00\nendstream"
        ),
        5: _stream(f"q {width:f} 0 0 {height:f} {x:f} {y:f} cm /Im Do Q".encode()),
    }
    return serialise(objects)


_PAD = bytes.fromhex("28BF4E5E4E758A4164004E56FFFA01082E2E00B6D0683E802F0CA9FE6453697A")
_FILE_ID = bytes(range(16))
_PERMISSIONS = -4


def build_encrypted_pdf(user_password: str, pages: list[PageSpec] | None = None) -> bytes:
    """A PDF protected with a user password, by the standard handler (RC4, 40 bit).

    Every stream is encrypted with its own object key, as a real file is, so with the right
    password (the empty one included) a reader gets the pages back as `build_pdf` writes them.
    The owner password is the user password, which is all the password check needs.
    """
    user = _padded(user_password)
    owner_key = hashlib.md5(user, usedforsecurity=False).digest()[:5]
    owner_entry = _rc4(owner_key, user)
    key = hashlib.md5(
        user + owner_entry + struct.pack("<i", _PERMISSIONS) + _FILE_ID, usedforsecurity=False
    ).digest()[:5]
    user_entry = _rc4(key, _PAD)
    encrypt = (
        f"<< /Filter /Standard /V 1 /R 2 /P {_PERMISSIONS} "
        f"/O <{owner_entry.hex()}> /U <{user_entry.hex()}> >>"
    )
    objects = {
        number: _encrypt_stream(body, number, key)
        for number, body in build_objects(pages if pages is not None else [PageSpec()]).items()
    }
    return serialise(
        objects,
        trailer_extra=f"/Encrypt {encrypt} /ID [<{_FILE_ID.hex()}> <{_FILE_ID.hex()}>]",
    )


def _encrypt_stream(body: bytes, number: int, key: bytes) -> bytes:
    head, separator, rest = body.partition(b"stream\n")
    if not separator:
        return body
    data, tail_separator, tail = rest.rpartition(b"\nendstream")
    object_key = hashlib.md5(
        key + struct.pack("<I", number)[:3] + b"\x00\x00", usedforsecurity=False
    ).digest()[: len(key) + 5]
    return head + separator + _rc4(object_key, data) + tail_separator + tail


def _padded(password: str) -> bytes:
    return (password.encode("latin-1") + _PAD)[:32]


def _rc4(key: bytes, data: bytes) -> bytes:
    state = list(range(256))
    j = 0
    for i in range(256):
        j = (j + state[i] + key[i % len(key)]) % 256
        state[i], state[j] = state[j], state[i]
    out = bytearray()
    i = j = 0
    for byte in data:
        i = (i + 1) % 256
        j = (j + state[i]) % 256
        state[i], state[j] = state[j], state[i]
        out.append(byte ^ state[(state[i] + state[j]) % 256])
    return bytes(out)
