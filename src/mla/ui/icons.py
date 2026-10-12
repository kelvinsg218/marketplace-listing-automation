"""Lucide SVG icons (ISC licence) recoloured at runtime."""
from __future__ import annotations

import hashlib
import tempfile
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from mla.config.paths import resource_path
from mla.ui.theme import T


@lru_cache(maxsize=None)
def _svg(name: str) -> str:
    return resource_path("icons", f"{name}.svg").read_text(encoding="utf-8")


def _colored(name: str, color: str, stroke: float) -> bytes:
    svg = _svg(name).replace("currentColor", color).replace('stroke-width="2"', f'stroke-width="{stroke}"')
    return svg.encode("utf-8")


@lru_cache(maxsize=512)
def pixmap(name: str, color: str = T.text_2, size: int = 18, stroke: float = 1.75, dpr: float = 2.0) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(_colored(name, color, stroke)))
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    renderer.render(painter)
    painter.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def icon(name: str, color: str = T.text_2, size: int = 18, active_color: str | None = None) -> QIcon:
    result = QIcon()
    result.addPixmap(pixmap(name, color, size), QIcon.Mode.Normal, QIcon.State.Off)
    if active_color:
        result.addPixmap(pixmap(name, active_color, size), QIcon.Mode.Normal, QIcon.State.On)
        result.addPixmap(pixmap(name, active_color, size), QIcon.Mode.Active, QIcon.State.Off)
    result.addPixmap(pixmap(name, T.text_3, size), QIcon.Mode.Disabled, QIcon.State.Off)
    return result


def icon_file(name: str, color: str, size: int) -> str:
    """Write a recoloured PNG to a temp file (for QSS url()) and return its path."""
    key = hashlib.sha1(f"{name}{color}{size}".encode()).hexdigest()[:12]
    target = Path(tempfile.gettempdir()) / "mla-icons" / f"{name}-{key}.png"
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        pixmap(name, color, size, stroke=2.5).save(str(target), "PNG")
    return str(target)


ICON_SIZE = QSize(18, 18)
