"""Every decode filter pdfminer applies is bounded by the stream limit, and is pdfminer's under it.

SEC-1 (every route), AC-25 (the limit itself, exactly) and Risk 6 (the names the seam replaces).
These decode one stream in this process. The page, thread and command tests are elsewhere.
"""

import base64
import inspect
import itertools
import random
import subprocess
import sys
import zlib

import pdfminer.ascii85
import pdfminer.ccitt
import pdfminer.lzw
import pdfminer.runlength
import pdfminer.utils
import pytest
from pdfminer import pdftypes
from pdfminer.psparser import LIT

import pdfgen
from pdftext import adapter
from pdftext.errors import LimitExceededError
from pdftext.limits import Limits
from test_limits_run import BOMBS

MIB = 1 << 20
TEXT = b"the quick brown fox jumps over the lazy dog"  # 43 bytes: its ASCII85 ends in a part group
# Ten columns need a limit of 90 bytes or more, so the predictors' inputs are over that.
LONG_TEXT = TEXT * 3
PNG_ROWS = b"".join(bytes([row % 5]) + LONG_TEXT[row * 10 : row * 10 + 10] for row in range(10))
TIFF_ROWS = LONG_TEXT[:100]
ASCII85_TEXT = base64.a85encode(TEXT, adobe=True)
DEFLATED = zlib.compress(TEXT)
TRUNCATED_DEFLATE = zlib.compress(TEXT * 20)[:-6]
BAD_CHECKSUM_DEFLATE = DEFLATED[:-1] + bytes([DEFLATED[-1] ^ 0xFF])
Stream = pdfgen.EncodedStream


def stream_of(encoded: Stream) -> pdftypes.PDFStream:
    attributes: dict[str, object] = {"Filter": [LIT(name) for name in encoded.filters]}
    if encoded.parms:
        attributes["DecodeParms"] = dict(encoded.parms)
    return pdftypes.PDFStream(attributes, encoded.data)


def decode_under(limit: int, encoded: Stream) -> bytes:
    with adapter._bounded_streams(limit):
        return stream_of(encoded).get_data()


@pytest.fixture
def pdfminer_alone(monkeypatch):
    """Decode as pdfminer does, while every name this seam replaces is put back."""

    def decode(encoded):
        with monkeypatch.context() as unpatched:
            for name, original in adapter._PDFMINER_FILTERS.items():
                unpatched.setattr(pdftypes, name, original)
            unpatched.setattr(pdftypes, "zlib", zlib)
            return stream_of(encoded).get_data()

    return decode


# Each stream with the largest output of any of its stages, which is the least limit it reads at.
STREAMS_WITH_THEIR_LIMIT = {
    "flate": (Stream(DEFLATED, ("FlateDecode",)), len(TEXT)),
    "flate-truncated": (
        Stream(TRUNCATED_DEFLATE, ("FlateDecode",)),
        len(zlib.decompressobj().decompress(TRUNCATED_DEFLATE)),
    ),
    "flate-bad-checksum": (Stream(BAD_CHECKSUM_DEFLATE, ("FlateDecode",)), len(TEXT)),
    "lzw": (pdfgen.lzw_bomb(5000), 5000),
    "run-length": (Stream(b"\x02abc\xfdz\x00!\x80", ("RunLengthDecode",)), 8),
    "ascii85": (Stream(ASCII85_TEXT, ("ASCII85Decode",)), len(TEXT)),
    "ascii85-with-zeros": (
        Stream(base64.a85encode(bytes(8) + TEXT, adobe=True), ("ASCII85Decode",)),
        8 + len(TEXT),
    ),
    "ascii-hex": (Stream(TEXT.hex().encode() + b">", ("ASCIIHexDecode",)), len(TEXT)),
    "ascii-hex-odd-digits": (Stream(b"61 6\n2 6>", ("ASCIIHexDecode",)), 3),
    "ascii-hex-with-no-marker": (Stream(b"61 62\n63", ("ASCIIHexDecode",)), 3),
    # Whatever follows the marker is dropped, so it counts for nothing, however long.
    "ascii-hex-with-bytes-after-the-marker": (
        Stream(b"616263>" + b"x" * 1000, ("ASCIIHexDecode",)),
        3,
    ),
    "png-predictor": (
        Stream(zlib.compress(PNG_ROWS), ("FlateDecode",), {"Predictor": 12, "Columns": 10}),
        len(PNG_ROWS),
    ),
    "tiff-predictor": (
        Stream(zlib.compress(TIFF_ROWS), ("FlateDecode",), {"Predictor": 2, "Columns": 10}),
        len(TIFF_ROWS),
    ),
    "png-predictor-after-a-pass-through-filter": (
        Stream(PNG_ROWS, ("DCTDecode",), {"Predictor": 12, "Columns": 10}),
        len(PNG_ROWS),
    ),
    "tiff-predictor-after-a-pass-through-filter": (
        Stream(TIFF_ROWS, ("DCTDecode",), {"Predictor": 2, "Columns": 10}),
        len(TIFF_ROWS),
    ),
    "flate-then-ascii85": (
        Stream(zlib.compress(ASCII85_TEXT), ("FlateDecode", "ASCII85Decode")),
        len(ASCII85_TEXT),
    ),
    "ascii-hex-then-flate": (
        Stream(DEFLATED.hex().encode() + b">", ("ASCIIHexDecode", "FlateDecode")),
        len(DEFLATED),
    ),
    # Each stage is held to the limit, so the last can be the one that passes it: 20 bytes of
    # Flate output become 1,280 of RunLength output.
    "flate-then-run-length-which-is-the-larger-stage": (
        Stream(zlib.compress(b"\x81 " * 10), ("FlateDecode", "RunLengthDecode")),
        1280,
    ),
}
SAME_AS_PDFMINERS = {
    **{name: stream for name, (stream, _) in STREAMS_WITH_THEIR_LIMIT.items()},
    "flate-corrupt-in-the-middle": Stream(
        DEFLATED[:12] + b"\xff\xff" + DEFLATED[14:], ("FlateDecode",)
    ),
    # An error well before the last 3 bytes is not forgiven: pdfminer gives nothing.
    "flate-with-a-reserved-block-type": Stream(b"\x78\x9c\x07" + DEFLATED[3:], ("FlateDecode",)),
    "not-flate-at-all": Stream(b"not zlib at all", ("FlateDecode",)),
}


@pytest.mark.parametrize(
    ("encoded", "limit"), STREAMS_WITH_THEIR_LIMIT.values(), ids=STREAMS_WITH_THEIR_LIMIT
)
class TestAStreamAtTheLimit:
    """AC-25"""

    def test_is_read_when_it_decodes_to_exactly_the_limit(self, pdfminer_alone, encoded, limit):
        assert len(pdfminer_alone(encoded)) <= limit

        assert decode_under(limit, encoded) == pdfminer_alone(encoded)

    def test_is_refused_when_it_decodes_to_one_byte_more(self, encoded, limit):
        with pytest.raises(LimitExceededError, match="a stream is too large"):
            decode_under(limit - 1, encoded)


class TestAStreamUnderTheLimit:
    """SEC-1, INV-1: the same bytes as pdfminer's, so the text is unchanged."""

    @pytest.mark.parametrize("encoded", SAME_AS_PDFMINERS.values(), ids=SAME_AS_PDFMINERS)
    def test_decodes_to_what_pdfminer_decodes_to(self, pdfminer_alone, encoded):
        assert decode_under(MIB, encoded) == pdfminer_alone(encoded)

    def test_a_stream_with_no_limit_set_is_decoded_by_pdfminer_alone(self, pdfminer_alone):
        encoded = pdfgen.ccitt_stream()

        assert adapter._stream_limit.max_bytes is None
        assert stream_of(encoded).get_data() == pdfminer_alone(encoded)


class TestEveryBombIsRefusedBecauseOfTheLimit:
    """SEC-1: the command's error page would come as well from a stream pdfminer can't read."""

    @pytest.mark.parametrize("make_bomb", BOMBS.values(), ids=BOMBS)
    def test_is_refused_with_the_limit_error_at_the_default(self, make_bomb):
        with pytest.raises(LimitExceededError, match="a stream is too large"):
            decode_under(Limits().max_stream_bytes, make_bomb())


class TestCcittFax:
    def test_is_refused_under_any_limit(self):
        with pytest.raises(LimitExceededError, match="a stream is too large"):
            decode_under(Limits().max_stream_bytes, pdfgen.ccitt_stream())


class TestACorruptedFlateStream:
    def test_that_decodes_past_the_limit_is_refused_while_it_is_decoded(self):
        packed = pdfgen.inflating_content(b"", 3 * MIB)[:-6]

        with adapter._bounded_streams(MIB), pytest.raises(LimitExceededError):
            adapter._bounded_decompress_corrupted(packed)

    def test_under_the_limit_is_decoded_as_pdfminer_decodes_it(self, pdfminer_alone):
        packed = pdfgen.inflating_content(b"", 3 * MIB)[:-6]

        with adapter._bounded_streams(4 * MIB):
            bounded = adapter._bounded_decompress_corrupted(packed)

        assert bounded == adapter._PDFMINER_FILTERS["decompress_corrupted"](packed)
        assert len(bounded) == 3 * MIB

    def test_is_read_at_exactly_the_limit_and_refused_one_byte_over(self):
        """AC-25"""
        packed = pdfgen.inflating_content(b"", 3 * MIB)[:-6]

        with adapter._bounded_streams(3 * MIB):
            assert len(adapter._bounded_decompress_corrupted(packed)) == 3 * MIB
        with adapter._bounded_streams(3 * MIB - 1), pytest.raises(LimitExceededError):
            adapter._bounded_decompress_corrupted(packed)


class TestAPredictor:
    """PNG's builds 9 bytes per column before it reads any data, so `Columns` is bounded too."""

    LIMIT = MIB
    WIDEST = LIMIT // 9

    def test_with_the_widest_allowed_columns_is_read(self):
        row = b"\x00" + b"\x01" * self.WIDEST

        with adapter._bounded_streams(self.LIMIT):
            decoded = pdftypes.apply_png_predictor(12, 1, self.WIDEST, 8, row)

        assert decoded == b"\x01" * self.WIDEST

    def test_png_with_one_column_more_is_refused_from_a_few_bytes(self):
        with adapter._bounded_streams(self.LIMIT), pytest.raises(LimitExceededError):
            pdftypes.apply_png_predictor(12, 1, self.WIDEST + 1, 8, b"\x00\x01")

    def test_tiff_with_one_column_more_is_refused_from_a_few_bytes(self):
        with adapter._bounded_streams(self.LIMIT), pytest.raises(LimitExceededError):
            pdftypes.apply_tiff_predictor(1, self.WIDEST + 1, 8, b"\x01")


class TestRunLengthSizedFromItsHeaders:
    @pytest.mark.parametrize("decoded", [1, 2, 127, 128, 129, 1000])
    def test_is_exactly_as_long_as_pdfminer_decodes_it(self, pdfminer_alone, decoded):
        encoded = pdfgen.run_length_bomb(decoded)

        assert len(pdfminer_alone(encoded)) == decoded
        assert decode_under(decoded, encoded) == pdfminer_alone(encoded)
        with pytest.raises(LimitExceededError):
            decode_under(decoded - 1, encoded)


A_GROUP = b"s8W-!"  # the digits of four 0xFF bytes
ASCII85_INPUTS = {
    "valid": ASCII85_TEXT,
    "with a part group last": base64.a85encode(b"abcde"),
    "empty": b"",
    "only the markers": b"<~~>",
    "z for four zero bytes": b"zz",
    "z between groups": A_GROUP + b"z" + A_GROUP,
    "z inside a group": b"ab" + b"z" + b"cde",
    "z inside a group after a good one": A_GROUP + b"abz" + b"cde",
    "a character that is not a digit": b"ab{cd",
    "a character that is not a digit, then z in the group": b"ab\x01z",
    "a part group then z": b"abz",
    "one digit alone": b"a",
    "a group over 2^32": b"uuuuu",
    "whitespace between digits": b" a\tb\nc\rd\x0be ",
    "whitespace inside the markers": b" < ~ " + A_GROUP + b" ~ > ",
    "a form feed, which pdfminer strips at the ends": b"\x0c" + A_GROUP + b"~>",
    "a form feed in the middle": A_GROUP + b"\x0c" + A_GROUP,
    "a y, which is not a digit here": b"y",
    "a marker in the middle": A_GROUP + b"~>" + A_GROUP,
}


def outcome_of(decode, data):
    try:
        return ("decoded", decode(data))
    except ValueError as error:
        return ("ValueError", str(error))


def pdfminer_strip(data):
    return pdfminer.ascii85.end_re.sub(b"", pdfminer.ascii85.start_re.sub(b"", data))


class TestAscii85MarkerStrip:
    """SEC-20, INV-1: the linear strip removes exactly what pdfminer's two regexes remove."""

    # Every way whitespace, a marker half and a digit can meet, including the form feed and the
    # vertical tab that `\s` counts as whitespace.
    ALPHABET = b" \n\x0c\x0b<~>a"

    def test_pins_the_regexes_it_stands_for(self):
        """Risk 6: a pdfminer release that changes either pattern fails here, not in the text."""
        assert pdfminer.ascii85.start_re.pattern == rb"^\s*<?\s*~\s*"
        assert pdfminer.ascii85.end_re.pattern == rb"\s*~\s*>?\s*$"
        assert pdfminer.ascii85.start_re.flags == pdfminer.ascii85.end_re.flags == 0

    def test_matches_the_regexes_on_every_input_up_to_six_bytes_over_the_hostile_alphabet(self):
        for length in range(7):
            for symbols in itertools.product(self.ALPHABET, repeat=length):
                data = bytes(symbols)
                assert adapter._strip_ascii85_markers(data) == pdfminer_strip(data), data

    def test_matches_the_regexes_on_random_input(self):
        generator = random.Random(7)  # noqa: S311 - seeded, so a failure repeats
        for index in range(20_000):
            alphabet = bytes(range(256)) if index % 2 else self.ALPHABET
            data = bytes(generator.choice(alphabet) for _ in range(generator.randrange(40)))
            assert adapter._strip_ascii85_markers(data) == pdfminer_strip(data), data

    @pytest.mark.parametrize("data", [b"", b"~", b"<~", b"<~~>", b" < ~ ~ > "])
    def test_leaves_nothing_of_input_that_is_only_markers_and_whitespace(self, data):
        assert adapter._strip_ascii85_markers(data) == pdfminer_strip(data) == b""

    def test_scans_32_mib_of_whitespace_in_well_under_a_second(self):
        """The regexes take minutes on this, in one C call. A child, so a regression can't hang."""
        code = (
            "import time\n"
            "from pdftext import adapter\n"
            "data = b' ' * (32 << 20) + b'!'\n"
            "started = time.perf_counter()\n"
            "stripped = adapter._strip_ascii85_markers(data)\n"
            "print(time.perf_counter() - started, len(stripped))\n"
        )

        run = subprocess.run(  # noqa: S603 - fixed interpreter and source
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=30, check=True
        )

        seconds, stripped = run.stdout.split(maxsplit=1)
        assert int(stripped) == (32 << 20) + 1  # no marker, so nothing is removed
        assert float(seconds) < 1

    def test_a_32_mib_whitespace_stream_decodes_to_nothing_in_under_a_second(self):
        """SEC-20, through the filter `decode` calls, in a child for the same reason."""
        code = (
            "import time\n"
            "from pdfminer import pdftypes\n"
            "from pdftext import adapter\n"
            "data = b' ' * (32 << 20) + b'!'\n"
            "started = time.perf_counter()\n"
            "with adapter._bounded_streams(32 << 20):\n"
            "    decoded = pdftypes.ascii85decode(data)\n"
            "print(time.perf_counter() - started, decoded)\n"
        )

        run = subprocess.run(  # noqa: S603 - fixed interpreter and source
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=30, check=True
        )

        seconds, decoded = run.stdout.split(maxsplit=1)
        assert decoded.strip() == "b''"
        assert float(seconds) < 1


class TestAscii85InSlices:
    """It gives pdfminer's bytes, or its `ValueError`, whatever the input and wherever it is cut."""

    @pytest.fixture(autouse=True)
    def two_groups_to_a_slice(self, monkeypatch):
        monkeypatch.setattr(adapter, "_ASCII85_SLICE", 10)

    @pytest.mark.parametrize("data", ASCII85_INPUTS.values(), ids=ASCII85_INPUTS)
    def test_matches_pdfminer_on_each_kind_of_input(self, pdfminer_alone, data):
        with adapter._bounded_streams(MIB):
            bounded = outcome_of(pdftypes.ascii85decode, data)

        assert bounded == outcome_of(adapter._PDFMINER_FILTERS["ascii85decode"], data)

    def test_matches_pdfminer_when_a_run_is_longer_than_a_slice(self):
        data = base64.a85encode(bytes(range(256)) * 3) + b"z" + base64.a85encode(TEXT)
        original = adapter._PDFMINER_FILTERS["ascii85decode"]

        with adapter._bounded_streams(MIB):
            assert pdftypes.ascii85decode(data) == original(data)

    def test_matches_pdfminer_on_random_input(self):
        original = adapter._PDFMINER_FILTERS["ascii85decode"]
        digits = bytes(range(33, 118)) + b"z \t\n\r\x0b\x0c~<>y{"
        generator = random.Random(4)  # noqa: S311 - seeded, so a failure repeats
        for _ in range(2000):
            data = bytes(generator.choice(digits) for _ in range(generator.randrange(60)))
            with adapter._bounded_streams(MIB):
                bounded = outcome_of(pdftypes.ascii85decode, data)
            assert bounded == outcome_of(original, data), data

    @pytest.mark.parametrize(
        "prefix", [b"", b" ", b"<~", b" < ~ ", b"~", b"<", b"\x0c~", b"<~\n", b"< \x0b"]
    )
    @pytest.mark.parametrize("suffix", [b"", b"~>", b" ~ > ", b"~", b">", b"\n~>\n", b" ", b"\x0c"])
    def test_matches_pdfminer_with_markers_and_whitespace_around_random_input(self, prefix, suffix):
        original = adapter._PDFMINER_FILTERS["ascii85decode"]
        digits = bytes(range(33, 118)) + b"z \t\n\r\x0b\x0c~<>y{"
        generator = random.Random(8)  # noqa: S311 - seeded, so a failure repeats
        for _ in range(100):
            body = bytes(generator.choice(digits) for _ in range(generator.randrange(30)))
            data = prefix + body + suffix
            with adapter._bounded_streams(MIB):
                bounded = outcome_of(pdftypes.ascii85decode, data)
            assert bounded == outcome_of(original, data), data

    def test_matches_pdfminer_on_random_valid_input(self):
        original = adapter._PDFMINER_FILTERS["ascii85decode"]
        generator = random.Random(5)  # noqa: S311 - seeded, so a failure repeats
        for _ in range(500):
            plain = bytes(
                generator.choice([0, 0, 0, 0, generator.randrange(256)])
                for _ in range(generator.randrange(80))
            )
            data = base64.a85encode(plain, adobe=generator.random() < 0.5)
            with adapter._bounded_streams(MIB):
                assert pdftypes.ascii85decode(data) == original(data) == plain


class TestAscii85SizedBeforeItIsDecoded:
    """AC-25: whatever the mix of `z`, whole groups and a part group, the size is exact."""

    def test_is_read_at_exactly_its_decoded_size_and_refused_one_byte_under(self):
        generator = random.Random(6)  # noqa: S311 - seeded, so a failure repeats
        for _ in range(300):
            plain = bytes(
                generator.choice([0, 0, 0, 0, generator.randrange(256)])
                for _ in range(generator.randrange(1, 80))
            )
            data = base64.a85encode(plain, adobe=generator.random() < 0.5)
            with adapter._bounded_streams(len(plain)):
                assert pdftypes.ascii85decode(data) == plain
            with adapter._bounded_streams(len(plain) - 1), pytest.raises(LimitExceededError):
                pdftypes.ascii85decode(data)


THE_NINE_NAMES = {
    "zlib",
    "decompress_corrupted",
    "lzwdecode",
    "rldecode",
    "ascii85decode",
    "asciihexdecode",
    "ccittfaxdecode",
    "apply_png_predictor",
    "apply_tiff_predictor",
}
ORIGINALS_BY_NAME = {
    "lzwdecode": pdfminer.lzw.lzwdecode,
    "rldecode": pdfminer.runlength.rldecode,
    "ascii85decode": pdfminer.ascii85.ascii85decode,
    "asciihexdecode": pdfminer.ascii85.asciihexdecode,
    "ccittfaxdecode": pdfminer.ccitt.ccittfaxdecode,
    "apply_png_predictor": pdfminer.utils.apply_png_predictor,
    "apply_tiff_predictor": pdfminer.utils.apply_tiff_predictor,
}
ARGUMENTS_BY_NAME = {
    "decompress_corrupted": (b"data",),
    "lzwdecode": (b"data",),
    "rldecode": (b"data",),
    "ascii85decode": (b"data",),
    "asciihexdecode": (b"data",),
    "ccittfaxdecode": (b"data", {"K": -1}),
    "apply_png_predictor": (12, 1, 8, 8, b"data"),
    "apply_tiff_predictor": (1, 8, 8, b"data"),
}


class TestTheSeam:
    """Risk 6: pdfminer looks these names up in `pdftypes` at call time, and each is replaced."""

    def test_replaces_nine_names(self):
        assert {each.name for each in adapter._DECODE_FILTERS} == THE_NINE_NAMES

    @pytest.mark.parametrize("name", sorted(THE_NINE_NAMES))
    def test_each_name_is_one_that_decode_looks_up_and_is_replaced(self, name):
        assert name in pdftypes.PDFStream.decode.__code__.co_names
        replacement = next(each.bounded for each in adapter._DECODE_FILTERS if each.name == name)
        assert getattr(pdftypes, name) is replacement

    @pytest.mark.parametrize("name", sorted(THE_NINE_NAMES - {"zlib", "decompress_corrupted"}))
    def test_each_original_is_the_function_from_its_home_module(self, name):
        """Read from `pdftypes`, so it is also the function `decode` called before the seam."""
        assert adapter._PDFMINER_FILTERS[name] is ORIGINALS_BY_NAME[name]

    def test_the_zlib_shim_stands_in_for_the_standard_library_module(self):
        shim = pdftypes.zlib

        assert shim is next(each.bounded for each in adapter._DECODE_FILTERS if each.name == "zlib")
        assert shim.decompressobj is zlib.decompressobj
        assert shim.error is zlib.error

    def test_the_original_retry_for_corrupt_flate_is_pdfminers_own(self):
        original = adapter._PDFMINER_FILTERS["decompress_corrupted"]

        assert (original.__module__, original.__name__) == (
            "pdfminer.pdftypes",
            "decompress_corrupted",
        )
        assert original is not pdftypes.decompress_corrupted

    @pytest.mark.parametrize("name", sorted(ARGUMENTS_BY_NAME))
    def test_with_no_limit_each_calls_pdfminers_original_with_the_same_arguments(
        self, monkeypatch, name
    ):
        monkeypatch.setitem(adapter._PDFMINER_FILTERS, name, lambda *args: ("original", args))

        assert adapter._stream_limit.max_bytes is None
        assert getattr(pdftypes, name)(*ARGUMENTS_BY_NAME[name]) == (
            "original",
            ARGUMENTS_BY_NAME[name],
        )

    def test_every_name_with_arguments_to_test_is_one_of_the_nine(self):
        assert set(ARGUMENTS_BY_NAME) | {"zlib"} == THE_NINE_NAMES

    def test_each_replacement_takes_the_arguments_pdfminer_gives_its_original(self):
        for name, original in adapter._PDFMINER_FILTERS.items():
            replacement = getattr(pdftypes, name)
            assert list(inspect.signature(replacement).parameters) == list(
                inspect.signature(original).parameters
            ), name


class TestTheBombBuilders:
    """The streams the other tests rely on decode to exactly what they say."""

    @pytest.mark.parametrize("build", [pdfgen.run_length_bomb, pdfgen.lzw_bomb])
    @pytest.mark.parametrize("decoded", [341, 5000, 100_000, 8_000_000])
    def test_decode_to_their_prefix_and_then_spaces_to_the_size_asked_for(
        self, pdfminer_alone, build, decoded
    ):
        prefix = b"BT (hello) Tj ET " * 20

        assert pdfminer_alone(build(decoded, prefix)) == prefix + b" " * (decoded - len(prefix))
        assert pdfminer_alone(build(decoded)) == b" " * decoded

    def test_flate_repeated_inflates_to_the_unit_repeated(self):
        assert zlib.decompress(pdfgen.repeated_flate(b"\x81 ", 3 * MIB + 10)) == b"\x81 " * (
            (3 * MIB + 10) // 2
        )
