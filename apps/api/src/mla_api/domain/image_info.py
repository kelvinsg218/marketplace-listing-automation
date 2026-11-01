"""Image format and dimensions from the file header (PNG, JPEG, WEBP), without Pillow.

Migrated from the discontinued desktop app (src/mla, removed on 2026-11-01); logic unchanged unless noted. Adapted to read from bytes.
"""
from __future__ import annotations

import io
import struct
from dataclasses import dataclass


class ImageError(ValueError):
    pass


@dataclass(frozen=True)
class ImageInfo:
    format: str
    width: int
    height: int


def _read(fh, name: str) -> ImageInfo:
    head = fh.read(64)
    if head.startswith(b"\x89PNG\r\n\x1a\n") and head[12:16] == b"IHDR":
        width, height = struct.unpack(">II", head[16:24])
        return ImageInfo("png", width, height)
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ImageInfo("webp", *_webp_size(head))
    if head[:2] == b"\xff\xd8":
        fh.seek(2)
        return ImageInfo("jpeg", *_jpeg_size(fh))
    raise ImageError(f"Arquivo não é uma imagem JPG, PNG ou WEBP válida: {name}")


def _webp_size(head: bytes) -> tuple[int, int]:
    chunk = head[12:16]
    if chunk == b"VP8 " and head[23:26] == b"\x9d\x01\x2a":
        w, h = struct.unpack("<HH", head[26:30])
        return w & 0x3FFF, h & 0x3FFF
    if chunk == b"VP8L" and head[20] == 0x2F:
        bits = int.from_bytes(head[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if chunk == b"VP8X":
        w = int.from_bytes(head[24:27], "little") + 1
        h = int.from_bytes(head[27:30], "little") + 1
        return w, h
    raise ImageError("WEBP com formato não reconhecido")


_SOF_MARKERS = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def _jpeg_size(fh) -> tuple[int, int]:
    while True:
        byte = fh.read(1)
        if not byte:
            break
        if byte != b"\xff":
            continue
        marker = fh.read(1)
        while marker == b"\xff":
            marker = fh.read(1)
        if not marker:
            break
        code = marker[0]
        if code in (0xD8, 0x01) or 0xD0 <= code <= 0xD7:
            continue
        length_bytes = fh.read(2)
        if len(length_bytes) < 2:
            break
        length = struct.unpack(">H", length_bytes)[0]
        if code in _SOF_MARKERS:
            data = fh.read(5)
            height, width = struct.unpack(">HH", data[1:5])
            return width, height
        fh.seek(length - 2, 1)
    raise ImageError("JPEG sem cabeçalho de dimensões")


def read_image_info_bytes(data: bytes) -> ImageInfo:
    return _read(io.BytesIO(data), "imagem")


def read_image_info(path) -> ImageInfo:
    with open(path, "rb") as fh:
        return _read(fh, getattr(path, "name", str(path)))
