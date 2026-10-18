from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest

from mla.config.paths import AppPaths
from mla.core.enums import Marketplace
from mla.core.models import Product, ProductMarketplaceData
from mla.services.context import AppContext


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


def make_pdf(path: Path, lines: list[tuple[int, int, str]]) -> Path:
    """Write a one-page text PDF (Helvetica, WinAnsi); lines are (x, y, text) in points."""
    def escape(text: str) -> str:
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    stream = "\n".join(f"BT /F1 10 Tf {x} {y} Td ({escape(t)}) Tj ET" for x, y, t in lines).encode("cp1252")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >>"
        b" /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(out))
    return path


def pdf_table(path: Path, rows: list[tuple[str, ...]], columns: tuple[int, ...] = (50, 150, 380, 470),
              title: str = "Catálogo Auto Peças Horizonte (fictício)") -> Path:
    lines = [(50, 800, title)]
    y = 760
    for row in rows:
        lines += [(x, y, cell) for x, cell in zip(columns, row) if cell]
        y -= 18
    return make_pdf(path, lines)


@pytest.fixture
def pdf_builder():
    return pdf_table, make_pdf


@pytest.fixture
def paths(tmp_path: Path) -> AppPaths:
    return AppPaths(tmp_path / "data").ensure()


@pytest.fixture
def ctx(paths: AppPaths):
    context = AppContext.open(paths)
    yield context
    context.close()


@pytest.fixture
def png(tmp_path: Path):
    counter = {"n": 0}

    def factory(width: int = 800, height: int = 800) -> Path:
        counter["n"] += 1
        shade = (counter["n"] * 37) % 255
        return make_png(tmp_path / "src" / f"img{counter['n']}.png", width, height, (shade, 60, 180))

    return factory


@pytest.fixture
def complete_product(ctx: AppContext, png):
    """A product that passes catalog validation (status READY)."""
    def factory(sku: str = "SKU-1", **overrides) -> Product:
        product = Product(
            internal_name=f"Suporte {sku}", sku=sku, title="Suporte articulado para monitor",
            category="Informática", brand="Acme", description="Suporte de mesa em aço com ajuste de altura e giro.",
            price_cents=12990, stock=5, weight_g=1500, length_mm=400, width_mm=200, height_mm=100,
        )
        product.images.append(ctx.images.import_file(png()))
        product.marketplace_data[Marketplace.SIMULATED] = ProductMarketplaceData(Marketplace.SIMULATED, enabled=True)
        for key, value in overrides.items():
            setattr(product, key, value)
        return product
    return factory
