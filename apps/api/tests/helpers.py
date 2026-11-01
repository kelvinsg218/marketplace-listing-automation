"""Test helpers (make_png migrated from the desktop test-suite)."""
import struct
import zlib
from pathlib import Path


def make_png(path: Path, width: int = 800, height: int = 800, color: tuple[int, int, int] = (120, 80, 200)) -> Path:
    """Write a valid solid-colour RGB PNG without third-party libraries."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    row = b"\x00" + bytes(color) * width
    raw = zlib.compress(row * height, 9)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", raw) + chunk(b"IEND", b""))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)
    return path
