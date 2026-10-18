from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSizePolicy,
    QStyledItemDelegate, QVBoxLayout, QWidget,
)

from mla.ui.icons import ICON_SIZE, icon
from mla.ui.theme import T, TONES, tone_for


def repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def set_prop(widget: QWidget, name: str, value) -> None:
    widget.setProperty(name, value)
    repolish(widget)


def button(text: str, variant: str = "secondary", icon_name: str | None = None,
           on_click: Callable | None = None, tooltip: str = "") -> QPushButton:
    btn = QPushButton(text)
    if variant != "secondary":
        btn.setProperty("variant", variant)
    if icon_name:
        color = {"primary": "#FFFFFF", "danger": T.danger, "success": "#06140D"}.get(variant, T.text_2)
        btn.setIcon(icon(icon_name, color, 16))
        btn.setIconSize(QSize(16, 16))
    if on_click:
        btn.clicked.connect(on_click)
    if tooltip:
        btn.setToolTip(tooltip)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


def icon_button(icon_name: str, tooltip: str, on_click: Callable | None = None, color: str = T.text_2) -> QPushButton:
    btn = QPushButton()
    btn.setProperty("variant", "ghost")
    btn.setIcon(icon(icon_name, color, 16))
    btn.setIconSize(QSize(16, 16))
    btn.setToolTip(tooltip)
    btn.setAccessibleName(tooltip)
    btn.setFixedSize(30, 30)
    btn.setStyleSheet("padding: 0;")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    if on_click:
        btn.clicked.connect(on_click)
    return btn


def label(text: str = "", role: str | None = None, object_name: str | None = None, wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    if role:
        lbl.setProperty("role", role)
    if object_name:
        lbl.setObjectName(object_name)
    lbl.setWordWrap(wrap)
    return lbl


def divider() -> QFrame:
    line = QFrame()
    line.setObjectName("divider")
    return line


class StatusChip(QWidget):
    """Pill with a dot; colours come from the status tone map."""

    def __init__(self, status=None, text: str = "", tone: str | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self._text, self._fg, self._bg = "", T.text_2, T.raised
        self.set_status(status, text, tone)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_status(self, status=None, text: str = "", tone: str | None = None) -> None:
        self._text = text or (status.label if status is not None else "")
        self._fg, self._bg = TONES[tone] if tone else tone_for(status)
        self.setAccessibleName(self._text)
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:
        fm = QFontMetrics(self.font())
        return QSize(fm.horizontalAdvance(self._text) + 28, 22)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        paint_chip(painter, self.rect(), self._text, self._fg, self._bg, self.font())
        painter.end()


def paint_chip(painter: QPainter, rect: QRect, text: str, fg: str, bg: str, font) -> int:
    """Draw a status pill at rect's left/vertical centre. Returns the width used."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    fm = QFontMetrics(font)
    width = fm.horizontalAdvance(text) + 28
    pill = QRect(rect.left(), rect.center().y() - 11, width, 22)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(bg))
    painter.drawRoundedRect(pill, 11, 11)
    painter.setBrush(QColor(fg))
    painter.drawEllipse(pill.left() + 9, pill.center().y() - 3, 6, 6)
    painter.setPen(QColor(fg))
    painter.setFont(font)
    painter.drawText(pill.adjusted(20, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
    painter.restore()
    return width


class StatusDelegate(QStyledItemDelegate):
    """Paints a status chip for cells whose UserRole holds a status value.

    Qt hands StrEnum values back as plain str, so the delegate converts them
    with `enum_cls`. `tones` optionally maps status -> tone name.
    """

    def __init__(self, parent=None, enum_cls=None, tones: dict | None = None):
        super().__init__(parent)
        self.enum_cls = enum_cls
        self.tones = tones

    def _status(self, value):
        if value is None or value == "":
            return None
        if self.enum_cls is not None and not isinstance(value, self.enum_cls):
            try:
                return self.enum_cls(value)
            except ValueError:
                return None
        return value if hasattr(value, "label") else None

    def paint(self, painter: QPainter, option, index) -> None:
        status = self._status(index.data(Qt.ItemDataRole.UserRole))
        if status is None:
            super().paint(painter, option, index)
            return
        self.initStyleOption(option, index)
        option.text = ""
        option.widget.style().drawControl(option.widget.style().ControlElement.CE_ItemViewItem, option, painter,
                                          option.widget)
        fg, bg = TONES[self.tones[status]] if self.tones else tone_for(status)
        paint_chip(painter, option.rect.adjusted(8, 0, 0, 0), status.label, fg, bg, option.font)


def clear_layout(layout) -> None:
    """Remove every child now (deleteLater alone leaves widgets painted until the next loop turn)."""
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())
            item.layout().deleteLater()


def format_when(iso: str | None) -> str:
    """'2026-10-12T14:54:03' -> 'hoje, 14:54' / 'ontem, 09:10' / '03/10, 08:00' / '03/10/2025'."""
    if not iso:
        return ""
    from datetime import datetime, timedelta
    try:
        moment = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    today = datetime.now().date()
    if moment.date() == today:
        return f"hoje, {moment:%H:%M}"
    if moment.date() == today - timedelta(days=1):
        return f"ontem, {moment:%H:%M}"
    if moment.year == today.year:
        return f"{moment:%d/%m}, {moment:%H:%M}"
    return f"{moment:%d/%m/%Y}"


def plural(n: int, singular: str, plural_form: str) -> str:
    return f"{n} {singular if n == 1 else plural_form}"


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        text = QVBoxLayout()
        text.setSpacing(2)
        self.title = label(title, object_name="pageTitle")
        self.subtitle = label(subtitle, object_name="pageSubtitle")
        text.addWidget(self.title)
        text.addWidget(self.subtitle)
        self.subtitle.setVisible(bool(subtitle))
        layout.addLayout(text, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        layout.addLayout(self.actions)

    def add_action(self, widget: QWidget) -> QWidget:
        self.actions.addWidget(widget)
        return widget

    def set_subtitle(self, text: str) -> None:
        self.subtitle.setText(text)
        self.subtitle.setVisible(bool(text))


class Panel(QFrame):
    def __init__(self, title: str = "", flat: bool = False, parent: QWidget | None = None, margins: int = 16):
        super().__init__(parent)
        self.setObjectName("panelFlat" if flat else "panel")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(margins, margins, margins, margins)
        self.body.setSpacing(10)
        self.header = QHBoxLayout()
        self.header.setSpacing(8)
        if title:
            self.title = label(title, object_name="sectionTitle")
            self.header.addWidget(self.title, 1)
            self.body.addLayout(self.header)

    def add(self, widget: QWidget, stretch: int = 0) -> QWidget:
        self.body.addWidget(widget, stretch)
        return widget


class EmptyState(QWidget):
    def __init__(self, icon_name: str, title: str, message: str, action: QPushButton | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)
        glyph = QLabel()
        glyph.setPixmap(icon(icon_name, T.text_3, 32).pixmap(QSize(32, 32)))
        glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(glyph)
        heading = label(title, object_name="sectionTitle")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(heading)
        body = label(message, role="muted", wrap=True)
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.setMaximumWidth(420)
        layout.addWidget(body, 0, Qt.AlignmentFlag.AlignHCenter)
        if action is not None:
            layout.addSpacing(6)
            layout.addWidget(action, 0, Qt.AlignmentFlag.AlignHCenter)


class Callout(QFrame):
    """Inline note inside a form: violet for guidance, amber when the user must check something."""

    def __init__(self, text: str = "", warn: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("calloutWarn" if warn else "callout")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(10)
        glyph = QLabel()
        glyph.setPixmap(icon("triangle-alert" if warn else "info", T.warning if warn else T.violet_text, 16)
                        .pixmap(QSize(16, 16)))
        layout.addWidget(glyph, 0, Qt.AlignmentFlag.AlignTop)
        self.text = label(text, wrap=True)
        layout.addWidget(self.text, 1)

    def set_text(self, text: str) -> None:
        self.text.setText(text)
        self.setVisible(bool(text))


class StepRail(QWidget):
    """Numbered steps of a wizard; the current one is underlined in violet."""

    def __init__(self, steps: list[str], parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.labels = []
        for number, text in enumerate(steps, start=1):
            item = label(f"{number}  {text}")
            item.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            layout.addWidget(item, 1)
            self.labels.append(item)
        self.set_current(0)

    def set_current(self, index: int) -> None:
        for position, item in enumerate(self.labels):
            set_prop(item, "step", "done" if position < index else "current" if position == index else "todo")


class Toast(QLabel):
    """Short confirmation in the bottom-right corner; fades out by itself."""

    def __init__(self, parent: QWidget, text: str, tone: str = "neutral"):
        super().__init__(text, parent)
        self.setObjectName("toast")
        fg = {"success": T.success, "danger": T.danger, "warning": T.warning}.get(tone, T.text)
        self.setStyleSheet(f"color: {fg};")
        self.setWordWrap(True)
        self.setMaximumWidth(420)
        self.adjustSize()
        margin = 20
        self.move(parent.width() - self.width() - margin, parent.height() - self.height() - margin)
        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        self._fade = QPropertyAnimation(effect, b"opacity", self)
        self._fade.setDuration(220)
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.setEasingCurve(QEasingCurve.Type.InCubic)
        self._fade.finished.connect(self.deleteLater)
        self.show()
        self.raise_()
        QTimer.singleShot(3200, self._fade.start)


def show_toast(widget: QWidget, text: str, tone: str = "neutral") -> None:
    window = widget.window()
    Toast(window, text, tone)


def confirm(parent: QWidget, title: str, text: str, confirm_label: str, danger: bool = False) -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Icon.Warning if danger else QMessageBox.Icon.Question)
    ok = box.addButton(confirm_label, QMessageBox.ButtonRole.AcceptRole)
    ok.setProperty("variant", "danger" if danger else "primary")
    cancel = box.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel)
    box.exec()
    return box.clickedButton() is ok


def inform(parent: QWidget, title: str, text: str, error: bool = False) -> None:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Icon.Critical if error else QMessageBox.Icon.Information)
    box.addButton("Entendi", QMessageBox.ButtonRole.AcceptRole)
    box.exec()


@lru_cache(maxsize=512)
def _thumb(path: str, size: int, mtime: float) -> QPixmap:
    source = QPixmap(path)
    if source.isNull():
        return QPixmap()
    side = min(source.width(), source.height())
    square = source.copy((source.width() - side) // 2, (source.height() - side) // 2, side, side)
    scaled = square.scaled(size * 2, size * 2, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
    scaled.setDevicePixelRatio(2.0)
    return scaled


def thumbnail(path: Path, size: int) -> QPixmap:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return QPixmap()
    return _thumb(str(path), size, mtime)


__all__ = [
    "ICON_SIZE", "Callout", "EmptyState", "PageHeader", "Panel", "StatusChip", "StepRail", "button", "confirm",
    "divider",
    "icon_button", "inform", "label", "paint_chip", "repolish", "set_prop", "show_toast", "thumbnail",
    "StatusDelegate", "clear_layout", "format_when", "plural",
]
