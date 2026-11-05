"""Resource limits for one conversion."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Limits:
    max_pages: int = 10_000
    max_file_bytes: int = 1 << 30  # 1 GiB
    page_timeout_s: float = 30.0
    total_timeout_s: float = 1800.0
    max_memory_bytes: int = 2 << 30  # 2 GiB of peak RSS growth since open
    max_stream_bytes: int = 256 << 20  # 256 MiB per decompressed stream
    max_chars_per_page: int = 1_000_000
    max_table_depth: int = 16


DEFAULT_LIMITS = Limits()
