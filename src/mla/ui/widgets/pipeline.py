"""The listing pipeline: the dashboard's one bold element.

Two tracks share a baseline: the catalog (products by readiness) and the
listings (product × marketplace × account by automation state). Segment widths
are proportional to counts, with a floor so empty stages stay visible and
clickable. The bars grow once when data arrives.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QEasingCurve, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath
from PySide6.QtWidgets import QSizePolicy, QWidget

from mla.ui.theme import T, display_font


@dataclass
class Stage:
    key: str
    label: str
    count: int
    color: str


class PipelineRail(QWidget):
    stageClicked = Signal(str)

    TRACK_GAP = 28
    SEG_GAP = 4
    BAR_H = 10

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._tracks: list[tuple[str, list[Stage]]] = []
        self._progress = 1.0
        self._rects: list[tuple[QRectF, str]] = []
        self._hover: str | None = None
        self.setMouseTracking(True)
        self.setMinimumHeight(118)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(650)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)
        self._animated_once = False

    def set_tracks(self, tracks: list[tuple[str, list[Stage]]]) -> None:
        self._tracks = tracks
        accessible = "; ".join(f"{s.label}: {s.count}" for _, stages in tracks for s in stages)
        self.setAccessibleDescription(accessible)
        if not self._animated_once:
            self._animated_once = True
            self._anim.start()
        self.update()

    def _on_anim(self, value) -> None:
        self._progress = float(value)
        self.update()

    def sizeHint(self):
        size = super().sizeHint()
        size.setHeight(118)
        return size

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._rects.clear()
        if not self._tracks:
            painter.end()
            return
        total_width = self.width() - self.TRACK_GAP * (len(self._tracks) - 1)
        weights = [max(1, len(stages)) for _, stages in self._tracks]
        x = 0.0
        number_font = display_font(26, QFont.Weight.ExtraBold)
        label_font = QFont(self.font())
        label_font.setPixelSize(12)
        caption_font = QFont(self.font())
        caption_font.setPixelSize(12)
        caption_font.setWeight(QFont.Weight.DemiBold)
        fm_label = QFontMetrics(label_font)
        for (caption, stages), weight in zip(self._tracks, weights):
            track_w = total_width * weight / sum(weights)
            painter.setFont(caption_font)
            painter.setPen(QColor(T.text_3))
            painter.drawText(QRectF(x, 0, track_w, 18), Qt.AlignmentFlag.AlignLeft, caption)
            seg_x = x
            usable = track_w - self.SEG_GAP * (len(stages) - 1)
            widths = self._segment_widths(stages, usable, fm_label)
            for stage, seg_w in zip(stages, widths):
                bar_w = max(6.0, seg_w * self._progress)
                bar = QRectF(seg_x, 30, bar_w, self.BAR_H)
                color = QColor(stage.color if stage.count else T.raised_hi)
                if self._hover == stage.key:
                    color = color.lighter(125)
                path = QPainterPath()
                path.addRoundedRect(bar, 3, 3)
                painter.fillPath(path, color)
                painter.setFont(number_font)
                painter.setPen(QColor(T.text if stage.count else T.text_3))
                painter.drawText(QRectF(seg_x, 48, seg_w, 36), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                                 str(stage.count))
                painter.setFont(label_font)
                painter.setPen(QColor(T.text_2))
                text = fm_label.elidedText(stage.label, Qt.TextElideMode.ElideRight, int(seg_w) - 4)
                painter.drawText(QRectF(seg_x, 86, seg_w, 20), Qt.AlignmentFlag.AlignLeft, text)
                self._rects.append((QRectF(seg_x, 24, seg_w, 84), stage.key))
                seg_x += seg_w + self.SEG_GAP
            x += track_w + self.TRACK_GAP
        painter.end()

    @staticmethod
    def _segment_widths(stages: list[Stage], usable: float, fm: QFontMetrics) -> list[float]:
        """Every segment fits its label; the remaining width is shared in proportion to the counts."""
        minimums = [fm.horizontalAdvance(s.label) + 14.0 for s in stages]
        spare = usable - sum(minimums)
        if spare <= 0:
            return [usable * m / sum(minimums) for m in minimums]
        total = sum(s.count for s in stages)
        if not total:
            return [m + spare / len(stages) for m in minimums]
        return [m + spare * s.count / total for m, s in zip(minimums, stages)]

    def _key_at(self, pos) -> str | None:
        for rect, key in self._rects:
            if rect.contains(pos):
                return key
        return None

    def mouseMoveEvent(self, event) -> None:
        key = self._key_at(event.position())
        if key != self._hover:
            self._hover = key
            self.setCursor(Qt.CursorShape.PointingHandCursor if key else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, _event) -> None:
        self._hover = None
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        key = self._key_at(event.position())
        if key:
            self.stageClicked.emit(key)
