from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QHBoxLayout, QListView, QListWidget, QListWidgetItem, QVBoxLayout, QWidget,
)

from mla.core.models import ProductImage
from mla.services.images import ImageError, ImageStore
from mla.ui.icons import pixmap
from mla.ui.theme import T
from mla.ui.widgets.common import button, label, set_prop, show_toast, thumbnail

THUMB = 132
ROLE_IMAGE = Qt.ItemDataRole.UserRole + 1


class _ImageList(QListWidget):
    filesDropped = Signal(list)
    orderChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setIconSize(QSize(THUMB, THUMB))
        self.setGridSize(QSize(THUMB + 20, THUMB + 40))
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Snap)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setAcceptDrops(True)
        self.setSpacing(6)
        self.setWordWrap(True)
        self.setMinimumHeight(THUMB + 70)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            files = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
            event.acceptProposedAction()
            self.filesDropped.emit(files)
            return
        super().dropEvent(event)
        self.orderChanged.emit()


class ImageGallery(QWidget):
    changed = Signal()

    def __init__(self, store: ImageStore, parent: QWidget | None = None):
        super().__init__(parent)
        self.store = store
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        bar = QHBoxLayout()
        bar.addWidget(button("Adicionar imagens", "secondary", "image-plus", self._pick))
        self.main_btn = button("Definir como principal", "ghost", "star", self._make_main)
        self.remove_btn = button("Remover", "danger", "trash-2", self._remove)
        bar.addWidget(self.main_btn)
        bar.addWidget(self.remove_btn)
        bar.addStretch(1)
        self.count = label("", role="hint")
        bar.addWidget(self.count)
        layout.addLayout(bar)
        self.list = _ImageList()
        self.list.setObjectName("dropZone")
        self.list.filesDropped.connect(self.add_files)
        self.list.orderChanged.connect(self._emit)
        self.list.itemSelectionChanged.connect(self._sync_buttons)
        self.list.itemDoubleClicked.connect(lambda _item: self._make_main())
        layout.addWidget(self.list, 1)
        layout.addWidget(label("Arraste arquivos JPG, PNG ou WEBP para cá. Arraste as miniaturas para mudar a ordem; "
                               "a primeira imagem principal é a capa do anúncio.", role="hint", wrap=True))
        self._sync_buttons()

    # ---------------------------------------------------------------- data
    def set_images(self, images: list[ProductImage]) -> None:
        self.list.clear()
        for image in images:
            self._append(image)
        self._refresh_labels()

    def images(self) -> list[ProductImage]:
        result = []
        for row in range(self.list.count()):
            image: ProductImage = self.list.item(row).data(ROLE_IMAGE)
            image.position = row
            result.append(image)
        if result and not any(i.is_main for i in result):
            result[0].is_main = True
        return result

    def add_files(self, files: list[Path]) -> None:
        added, problems = 0, []
        existing = {self.list.item(r).data(ROLE_IMAGE).filename for r in range(self.list.count())}
        for path in files:
            try:
                image = self.store.import_file(path)
            except (ImageError, OSError) as exc:
                problems.append(str(exc))
                continue
            if image.filename in existing:
                continue
            existing.add(image.filename)
            image.is_main = self.list.count() == 0
            self._append(image)
            added += 1
        self._refresh_labels()
        if added:
            self._emit()
        if problems:
            show_toast(self, problems[0] + (f" (+{len(problems) - 1})" if len(problems) > 1 else ""), "danger")

    # ---------------------------------------------------------------- internals
    def _append(self, image: ProductImage) -> None:
        item = QListWidgetItem()
        item.setData(ROLE_IMAGE, image)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDragEnabled)
        item.setSizeHint(QSize(THUMB + 16, THUMB + 36))
        self.list.addItem(item)

    def _decorate(self, item: QListWidgetItem) -> None:
        image: ProductImage = item.data(ROLE_IMAGE)
        thumb = thumbnail(self.store.path_for(image.filename), THUMB)
        canvas = QPixmap(THUMB * 2, THUMB * 2)
        canvas.setDevicePixelRatio(2.0)
        canvas.fill(QColor(T.canvas))
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not thumb.isNull():
            painter.drawPixmap(0, 0, thumb)
        if image.is_main:
            painter.setBrush(QColor(T.violet))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(6, 6, 26, 26, 6, 6)
            painter.drawPixmap(11, 11, pixmap("star", "#FFFFFF", 16))
        painter.end()
        item.setIcon(QIcon(canvas))
        small = min(image.width, image.height) < 500 if image.width else False
        caption = f"{image.width}×{image.height}" + (" · pequena" if small else "")
        item.setText(("Principal  " if image.is_main else "") + caption)
        item.setForeground(QColor(T.warning if small else T.text_2))
        item.setToolTip(f"{image.filename}\n{image.size_bytes / 1024:.0f} KB")

    def _refresh_labels(self) -> None:
        for row in range(self.list.count()):
            self._decorate(self.list.item(row))
        n = self.list.count()
        self.count.setText(f"{n} imagem" if n == 1 else f"{n} imagens")
        set_prop(self.list, "active", n == 0)
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        selected = self.list.selectedItems()
        self.main_btn.setEnabled(len(selected) == 1)
        self.remove_btn.setEnabled(bool(selected))

    def _pick(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Escolher imagens", "", "Imagens (*.jpg *.jpeg *.png *.webp)")
        if files:
            self.add_files([Path(f) for f in files])

    def _make_main(self) -> None:
        selected = self.list.selectedItems()
        if len(selected) != 1:
            return
        for row in range(self.list.count()):
            item = self.list.item(row)
            item.data(ROLE_IMAGE).is_main = item is selected[0]
        self._refresh_labels()
        self._emit()

    def _remove(self) -> None:
        for item in self.list.selectedItems():
            self.list.takeItem(self.list.row(item))
        self._refresh_labels()
        self._emit()

    def _emit(self) -> None:
        self._refresh_labels_light()
        self.changed.emit()

    def _refresh_labels_light(self) -> None:
        n = self.list.count()
        self.count.setText(f"{n} imagem" if n == 1 else f"{n} imagens")
