"""A small hand-written PDF generator, so tests control exactly what a page holds.

Text is drawn with one simple font whose `/ToUnicode` map assigns every distinct
character in the document its own single-byte code. Any Unicode text, including
characters XML forbids, can therefore appear in a PDF that pdfminer reads back as given.
Coordinates are PDF user space: points, origin at the bottom left.
"""

import hashlib
import struct
import zlib
from collections.abc import Callable
from dataclasses import dataclass, field
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


_ADLER_MODULUS = 65521
_BLOCK = 1 << 20


def inflating_content(prefix: bytes, padding: int) -> bytes:
    """A zlib stream that inflates to `prefix` followed by `padding` spaces.

    The padding is written as one block repeated, so a multi-gigabyte bomb is made instantly and
    stays a few megabytes. Spaces are ignored by a content-stream parser, so `prefix` keeps its
    meaning.
    """
    compressor = zlib.compressobj(level=9, wbits=-15)  # raw deflate, wrapped below
    head = compressor.compress(prefix) + compressor.flush(zlib.Z_FULL_FLUSH)
    # A full flush resets the dictionary, so every block of spaces compresses to the same bytes.
    block = compressor.compress(b" " * _BLOCK) + compressor.flush(zlib.Z_FULL_FLUSH)
    blocks, rest = divmod(padding, _BLOCK)
    tail = compressor.compress(b" " * rest) + compressor.flush(zlib.Z_FINISH)
    body = head + block * blocks + tail
    return b"\x78\xda" + body + struct.pack(">I", _adler32_with_spaces(prefix, padding))


def _adler32_with_spaces(prefix: bytes, padding: int) -> int:
    """The Adler-32 of `prefix` followed by `padding` spaces, without building them."""
    checksum = zlib.adler32(prefix)
    low, high = checksum & 0xFFFF, checksum >> 16
    space = 32
    high = (high + padding * low + space * padding * (padding + 1) // 2) % _ADLER_MODULUS
    low = (low + padding * space) % _ADLER_MODULUS
    return (high << 16) | low


def content_object_id(page_index: int) -> int:
    """The object number of the content stream of page `page_index` in `build_objects`."""
    return page_object_id(page_index) + 1


def _stream_data(objects: dict[int, bytes], number: int) -> bytes:
    """The bytes between `stream` and `endstream` of an unfiltered stream object."""
    _, _, rest = objects[number].partition(b"stream\n")
    return rest.rpartition(b"\nendstream")[0]


def with_inflating_content(objects: dict[int, bytes], page_index: int, inflated: int) -> None:
    """Make page `page_index`'s content stream inflate to `inflated` bytes, with its text kept."""
    number = content_object_id(page_index)
    content = _stream_data(objects, number)
    compressed = inflating_content(content, inflated - len(content))
    objects[number] = (
        b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(compressed)
        + compressed
        + b"\nendstream"
    )


def content_of(objects: dict[int, bytes], page_index: int) -> bytes:
    """The unfiltered content stream of page `page_index`, as `build_objects` makes it."""
    return _stream_data(objects, content_object_id(page_index))


@dataclass(frozen=True)
class EncodedStream:
    """A stream as it sits in the file, with the filters that decode it, first to last.

    `parms` is written as one `/DecodeParms` dictionary, which PDF applies to every filter in turn.
    """

    data: bytes
    filters: tuple[str, ...]
    parms: dict[str, int] = field(default_factory=dict)

    def as_object(self, extra_entries: str = "") -> bytes:
        names = " ".join(f"/{name}" for name in self.filters)
        entries = f"{extra_entries} /Filter [{names}]"
        if self.parms:
            entries += " /DecodeParms << " + " ".join(f"/{k} {v}" for k, v in self.parms.items())
            entries += " >>"
        header = f"<< /Length {len(self.data)} {entries} >>\nstream\n".encode("ascii")
        return header + self.data + b"\nendstream"


def with_encoded_content(objects: dict[int, bytes], page_index: int, stream: EncodedStream) -> None:
    """Make `stream` page `page_index`'s content stream, in place of its text."""
    objects[content_object_id(page_index)] = stream.as_object()


_FLATE_END_BYTES = 6  # the empty last block and the checksum, which `inflating_content` ends with


def with_truncated_content(objects: dict[int, bytes], page_index: int, inflated: int) -> None:
    """Make page `page_index`'s content a Flate stream cut short of its end, text kept.

    It inflates to `inflated` bytes, as `with_inflating_content` makes, but the zlib call fails on
    the missing end, so the reader falls back to decoding it a byte at a time.
    """
    number = content_object_id(page_index)
    content = _stream_data(objects, number)
    whole = inflating_content(content, inflated - len(content))
    objects[number] = EncodedStream(whole[:-_FLATE_END_BYTES], ("FlateDecode",)).as_object()


def repeated_flate(unit: bytes, size: int) -> bytes:
    """A zlib stream that inflates to `size` bytes of `unit` repeated, at a few bytes per MiB.

    `unit` must divide a MiB and `size` must be a whole number of units.
    """
    if _BLOCK % len(unit) or size % len(unit):
        raise ValueError("`unit` must divide a MiB, and `size` must be a multiple of it")
    compressor = zlib.compressobj(level=9, wbits=-15)
    block = unit * (_BLOCK // len(unit))
    full_blocks, rest = divmod(size, _BLOCK)
    # A full flush resets the dictionary, so every block compresses to the same bytes.
    packed_block = compressor.compress(block) + compressor.flush(zlib.Z_FULL_FLUSH)
    tail = compressor.compress(block[:rest]) + compressor.flush(zlib.Z_FINISH)
    checksum = 1
    for _ in range(full_blocks):
        checksum = zlib.adler32(block, checksum)
    checksum = zlib.adler32(block[:rest], checksum)
    return b"\x78\xda" + packed_block * full_blocks + tail + struct.pack(">I", checksum)


def run_length_bomb(decoded: int, prefix: bytes = b"") -> EncodedStream:
    """A RunLength stream of `prefix` and spaces to `decoded` bytes, from 2 bytes per 128 spaces."""
    literals = b"".join(
        bytes([len(piece) - 1]) + piece
        for piece in (prefix[i : i + 128] for i in range(0, len(prefix), 128))
    )
    runs, rest = divmod(decoded - len(prefix), 128)
    last_run = b"" if rest == 0 else b"\x00 " if rest == 1 else bytes([257 - rest]) + b" "
    return EncodedStream(literals + b"\x81 " * runs + last_run + b"\x80", ("RunLengthDecode",))


def ascii85_bomb(decoded: int) -> EncodedStream:
    """An ASCII85 stream of `decoded` bytes (a multiple of 4), one `z` for each 4 of them."""
    return EncodedStream(b"z" * (decoded // 4) + b"~>", ("ASCII85Decode",))


_SPACE = 32
_CLEAR = 256  # the LZW code that empties the table


def lzw_bomb(decoded: int, prefix: bytes = b"") -> EncodedStream:
    """An LZW stream of `prefix` and spaces to `decoded` bytes, long once its code table is full.

    The codes after the first are each one longer than the last, until the table is full and one
    code of 3,839 bytes repeats. Widths follow pdfminer's decoder: 9 bits, then 10, 11 and 12 as
    its table grows by one entry for each code. The spaces start after a clear code.
    """
    codes = [_SPACE]
    size = 1
    code = 258
    while code < 4096 and size + code - 256 <= decoded - len(prefix):  # 258 is two bytes, 259 three
        codes.append(code)
        size += code - 256
        code += 1
    while size + 3839 <= decoded - len(prefix):
        codes.append(4095)
        size += 3839
    codes.extend([_SPACE] * (decoded - len(prefix) - size))
    bits = [(_CLEAR, 9), *_lzw_widths(list(prefix))]
    if prefix:
        bits.append((_CLEAR, _lzw_width(len(prefix))))
    bits.extend(_lzw_widths(codes))
    return EncodedStream(_pack_bits(bits), ("LZWDecode",))


def _lzw_widths(codes: list[int]) -> list[tuple[int, int]]:
    return [(code, _lzw_width(index)) for index, code in enumerate(codes)]


def _lzw_width(index: int) -> int:
    """The bits of the code after `index` others, past the clear code."""
    return 9 if index < 254 else 10 if index < 766 else 11 if index < 1790 else 12


def _pack_bits(codes: list[tuple[int, int]]) -> bytes:
    """`(value, width)` pairs written most significant bit first, the last byte zero padded."""
    packed = bytearray()
    pending = 0
    pending_bits = 0
    for value, width in codes:
        pending = (pending << width) | value
        pending_bits += width
        while pending_bits >= 8:
            pending_bits -= 8
            packed.append((pending >> pending_bits) & 0xFF)
        pending &= (1 << pending_bits) - 1
    if pending_bits:
        packed.append((pending << (8 - pending_bits)) & 0xFF)
    return bytes(packed)


def ccitt_stream() -> EncodedStream:
    """A CCITT Group 4 stream, a filter for bilevel images that no content stream uses."""
    return EncodedStream(b"\xff\xff", ("CCITTFaxDecode",), {"K": -1, "Columns": 8})


def predictor_bomb(columns: int) -> EncodedStream:
    """A few bytes of Flate with a PNG predictor over `columns` columns, which sizes its rows."""
    return EncodedStream(
        zlib.compress(bytes(16)), ("FlateDecode",), {"Predictor": 12, "Columns": columns}
    )


def with_char_flood(objects: dict[int, bytes], page_index: int, chars: int) -> None:
    """Make page `page_index` show `chars` characters, from a content stream of a few kilobytes.

    The characters are one repeated byte in a single string, so the stream compresses to almost
    nothing, and the page's own text is replaced.
    """
    number = content_object_id(page_index)
    compressed = zlib.compress(b"BT /F1 1 Tf 0 700 Td (" + b"A" * chars + b") Tj ET", 9)
    objects[number] = (
        b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(compressed)
        + compressed
        + b"\nendstream"
    )


def with_draw_fan_out(
    objects: dict[int, bytes], page_index: int, levels: int = 3, fan_out: int = 1000
) -> None:
    """Make page `page_index` draw `fan_out ** levels` empty forms, nested `levels` deep.

    Each form draws the next one `fan_out` times, so the page is a CPU bomb that is a few
    kilobytes in the file. The page's own text is replaced.
    """
    first = max(objects) + 1
    forms = range(first, first + levels + 1)  # the last one is empty
    for number in forms:
        is_leaf = number == forms[-1]
        draws = b"" if is_leaf else b"/Fm Do\n" * fan_out
        resources = (
            b"" if is_leaf else f"/Resources << /XObject << /Fm {number + 1} 0 R >> >>".encode()
        )
        objects[number] = (
            b"<< /Type /XObject /Subtype /Form /BBox [0 0 10 10] %s /Length %d >>\nstream\n"
            % (resources, len(draws))
            + draws
            + b"\nendstream"
        )
    page = objects[page_object_id(page_index)]
    objects[page_object_id(page_index)] = page.replace(
        b"/Resources << ", f"/Resources << /XObject << /Fm {first} 0 R >> ".encode()
    )
    objects[content_object_id(page_index)] = _stream(b"/Fm Do")


def with_reference_cycle(objects: dict[int, bytes]) -> str:
    """Add two objects that refer to each other, and return a reference into the cycle."""
    first = max(objects) + 1
    objects[first] = b"%d 0 R" % (first + 1)
    objects[first + 1] = b"%d 0 R" % first
    return f"{first} 0 R"


_PAD = bytes.fromhex("28BF4E5E4E758A4164004E56FFFA01082E2E00B6D0683E802F0CA9FE6453697A")
_FILE_ID = bytes(range(16))
_PERMISSIONS = -4


def build_encrypted_pdf(
    user_password: str,
    pages: list[PageSpec] | None = None,
    damage: Callable[[dict[int, bytes]], None] | None = None,
) -> bytes:
    """A PDF protected with a user password, by the standard handler (RC4, 40 bit).

    `damage` changes the numbered objects (as `build_objects` makes them) before they are encrypted.

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
    plain = build_objects(pages if pages is not None else [PageSpec()])
    if damage is not None:
        damage(plain)
    objects = {number: _encrypt_stream(body, number, key) for number, body in plain.items()}
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


def build_pdf_with_catalog_in_object_stream(inflated: int) -> bytes:
    """A one-page PDF whose catalog is in a compressed object stream that inflates to `inflated`.

    The reader meets the stream while it opens the file, before any page is read, so a limit on
    stream size has to hold there too.
    """
    return build_pdf_with_object_in_object_stream(1, inflated, [PageSpec()])


def build_pdf_with_object_in_object_stream(
    number: int,
    inflated: int,
    pages: list[PageSpec],
    encoded: EncodedStream | None = None,
) -> bytes:
    """A PDF made by `build_objects` whose object `number` is in an object stream.

    The stream inflates to `inflated` bytes, so it is a bomb when `inflated` is large. Or it is
    `encoded`, which then holds the object, as given. The file ends with a cross-reference stream,
    as a file with object streams does.
    """
    objects = build_objects(pages)
    body = objects.pop(number)
    header = b"%d 0 " % number
    if encoded is None:
        encoded = EncodedStream(
            inflating_content(header + body, inflated - len(header + body)), ("FlateDecode",)
        )
    stream_id = max(objects, default=0) + 1
    xref_id = stream_id + 1
    out = bytearray(b"%PDF-1.7\n")
    offsets = {}
    for object_number, object_body in objects.items():
        offsets[object_number] = len(out)
        out += b"%d 0 obj\n" % object_number + object_body + b"\nendobj\n"
    offsets[stream_id] = len(out)
    out += (
        b"%d 0 obj\n" % stream_id
        + encoded.as_object(f"/Type /ObjStm /N 1 /First {len(header)}")
        + b"\nendobj\n"
    )
    offsets[xref_id] = len(out)
    entries = bytearray(b"\x00\x00\x00\x00\x00\x00\xff")  # object 0, free
    for object_number in range(1, xref_id + 1):
        if object_number == number:  # in the object stream, at index 0
            entries += b"\x02" + stream_id.to_bytes(4, "big") + (0).to_bytes(2, "big")
        else:
            entries += b"\x01" + offsets[object_number].to_bytes(4, "big") + (0).to_bytes(2, "big")
    out += (
        b"%d 0 obj\n<< /Type /XRef /Size %d /W [1 4 2] /Root 1 0 R /Length %d >>\nstream\n"
        % (xref_id, xref_id + 1, len(entries))
        + bytes(entries)
        + b"\nendstream\nendobj\n"
    )
    out += b"startxref\n%d\n%%%%EOF\n" % offsets[xref_id]
    return bytes(out)
