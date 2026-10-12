"""Generate src/mla/resources/app.ico and app.png (the pipeline motif from the dashboard)."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "mla" / "resources"


def render(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size / 256
    bg = QPainterPath()
    bg.addRoundedRect(QRectF(8 * s, 8 * s, 240 * s, 240 * s), 56 * s, 56 * s)
    p.fillPath(bg, QColor("#16151C"))
    bars = [(64, 70, QColor("#5B49B8")), (112, 118, QColor("#7B5CFF")), (160, 166, QColor("#3DD68C"))]
    for top, width, color in bars:
        bar = QPainterPath()
        bar.addRoundedRect(QRectF(52 * s, top * s, (width + 40) * s, 30 * s), 15 * s, 15 * s)
        p.fillPath(bar, color)
    p.end()
    return img


def main() -> int:
    QGuiApplication(sys.argv[:1])
    render(256).save(str(OUT / "app.png"), "PNG")
    if not render(256).save(str(OUT / "app.ico"), "ICO"):
        print("falha ao gravar ICO")
        return 1
    print(f"ícone gerado em {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
