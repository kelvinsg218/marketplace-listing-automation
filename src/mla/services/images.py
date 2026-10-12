"""Image import: copy into the data folder, content-addressed, with metadata.

Dimensions are read from the file header (PNG, JPEG, WEBP) so the service layer
does not depend on Qt or Pillow.
"""
from __future__ import annotations

import hashlib
import shutil
import struct
from dataclasses import dataclass
from pathlib import Path

from mla.core.models import ProductImage
from mla.core.validation import ALLOWED_IMAGE_EXTENSIONS, MAX_IMAGE_BYTES


class ImageError(ValueError):
    pass


@dataclass(frozen=True)
class ImageInfo:
    format: str
    width: int
    height: int


def read_image_info(path: Path) -> ImageInfo:
    with path.open("rb") as fh:
        head = fh.read(64)
        if head.startswith(b"\x89PNG\r\n\x1a\n") and head[12:16] == b"IHDR":
            width, height = struct.unpack(">II", head[16:24])
            return ImageInfo("png", width, height)
        if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
            return ImageInfo("webp", *_webp_size(head))
        if head[:2] == b"\xff\xd8":
            fh.seek(2)
            return ImageInfo("jpeg", *_jpeg_size(fh))
    raise ImageError(f"Arquivo não é uma imagem JPG, PNG ou WEBP válida: {path.name}")


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


class ImageStore:
    def __init__(self, images_dir: Path):
        self.root = images_dir
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, filename: str) -> Path:
        return self.root / filename

    def import_file(self, source: Path) -> ProductImage:
        source = Path(source)
        if not source.is_file():
            raise ImageError(f"Arquivo não encontrado: {source}")
        ext = source.suffix.lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            raise ImageError(f"Formato não aceito: {source.name} (use JPG, PNG ou WEBP)")
        size = source.stat().st_size
        if size > MAX_IMAGE_BYTES:
            raise ImageError(f"Imagem acima de 10 MB: {source.name}")
        info = read_image_info(source)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        filename = f"{digest[:20]}{'.jpg' if ext == '.jpeg' else ext}"
        target = self.root / filename
        if not target.exists():
            tmp = target.with_suffix(target.suffix + ".tmp")
            shutil.copyfile(source, tmp)
            tmp.replace(target)
        return ProductImage(filename=filename, width=info.width, height=info.height,
                            size_bytes=size, sha256=digest)

    def remove_orphans(self, in_use: set[str]) -> int:
        removed = 0
        for path in self.root.iterdir():
            if path.is_file() and path.name not in in_use and not path.name.endswith(".tmp"):
                path.unlink(missing_ok=True)
                removed += 1
        return removed
