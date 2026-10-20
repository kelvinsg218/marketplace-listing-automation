"""Bulk edit of descriptive catalog fields, with a preview before anything is written."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QGridLayout, QHBoxLayout, QHeaderView, QLineEdit,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from mla.core.enums import CommercialStatus, Condition
from mla.services.catalog import BULK_FIELDS, CatalogError
from mla.ui.theme import T
from mla.ui.widgets.common import Callout, button, confirm, label, plural

_CHOICES = {"condition": list(Condition), "commercial_status": list(CommercialStatus)}


class BulkEditDialog(QDialog):
    def __init__(self, ctx, product_ids: list[int], parent=None):
        super().__init__(parent)
        self.ctx, self.product_ids = ctx, product_ids
        self.changed = 0
        self._previewed: dict | None = None
        self.setWindowTitle("Editar em lote")
        self.resize(820, 620)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(12)
        layout.addWidget(label("Editar em lote", object_name="sectionTitle"))
        layout.addWidget(label(
            f"{plural(len(product_ids), 'produto selecionado', 'produtos selecionados')}. Só campos descritivos: "
            "preço, estoque, GTIN e SKU não são alterados em lote. Cada alteração fica no histórico do produto.",
            role="muted", wrap=True))
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        self.fields: dict[str, tuple[QCheckBox, QLineEdit | QComboBox]] = {}
        for index, (name, text) in enumerate(BULK_FIELDS.items()):
            check = QCheckBox(text)
            if name in _CHOICES:
                editor = QComboBox()
                for option in _CHOICES[name]:
                    editor.addItem(option.label, option.value)
                editor.currentIndexChanged.connect(self._invalidate)
            else:
                editor = QLineEdit()
                editor.setPlaceholderText(f"Novo valor de {text.lower()}")
                editor.textChanged.connect(self._invalidate)
            editor.setEnabled(False)
            check.toggled.connect(editor.setEnabled)
            check.toggled.connect(self._invalidate)
            self.fields[name] = (check, editor)
            row, col = divmod(index, 2)
            grid.addWidget(check, row, col * 2)
            grid.addWidget(editor, row, col * 2 + 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        layout.addLayout(grid)
        preview_row = QHBoxLayout()
        self.preview_btn = button("Pré-visualizar alterações", "secondary", "eye", self._preview)
        preview_row.addWidget(self.preview_btn)
        self.summary = label("", role="hint")
        preview_row.addWidget(self.summary, 1)
        layout.addLayout(preview_row)
        self.note = Callout(warn=True)
        self.note.setVisible(False)
        layout.addWidget(self.note)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["SKU", "Produto", "Campo", "Antes", "Depois"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        for col, width in ((0, 120), (1, 200), (2, 130), (3, 140)):
            header.resizeSection(col, width)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(button("Cancelar", "ghost", None, self.reject))
        self.apply_btn = button("Aplicar", "primary", "check", self._apply)
        self.apply_btn.setEnabled(False)
        footer.addWidget(self.apply_btn)
        layout.addLayout(footer)

    def values(self) -> dict[str, object]:
        result: dict[str, object] = {}
        for name, (check, editor) in self.fields.items():
            if check.isChecked():
                result[name] = editor.currentData() if isinstance(editor, QComboBox) else editor.text()
        return result

    def _invalidate(self, *_args) -> None:
        self._previewed = None
        self.apply_btn.setEnabled(False)
        self.apply_btn.setText("Aplicar")

    def _preview(self) -> None:
        values = self.values()
        try:
            rows = self.ctx.catalog.bulk_preview(self.product_ids, values)
        except CatalogError as exc:
            self.note.set_text(str(exc))
            self.table.setRowCount(0)
            self.summary.setText("")
            return
        self.note.set_text("")
        self.table.setRowCount(len(rows))
        for r, change in enumerate(rows):
            for c, text in enumerate((change.sku, change.name, change.label, change.old or "(vazio)", change.new)):
                item = QTableWidgetItem(text)
                item.setToolTip(text if len(text) > 30 else "")
                if c == 3:
                    item.setForeground(QColor(T.text_3))
                self.table.setItem(r, c, item)
        products = len({change.product_id for change in rows})
        if rows:
            self.summary.setText(f"{plural(len(rows), 'alteração', 'alterações')} em "
                                 f"{plural(products, 'produto', 'produtos')}. Nada foi gravado ainda.")
            self._previewed = values
            self.apply_btn.setText(f"Aplicar em {plural(products, 'produto', 'produtos')}")
            self.apply_btn.setEnabled(True)
        else:
            self.summary.setText("Os produtos selecionados já têm esses valores; nada a alterar.")

    def _apply(self) -> None:
        if self._previewed is None or self._previewed != self.values():
            self._invalidate()
            return
        if not confirm(self, "Aplicar edição em lote", f"{self.apply_btn.text()}? A gravação é feita de uma vez: se "
                       "algo falhar, nenhum produto é alterado.", "Aplicar"):
            return
        try:
            self.changed = self.ctx.catalog.bulk_update(self.product_ids, self._previewed)
        except CatalogError as exc:
            self.note.set_text(str(exc))
            return
        self.accept()


__all__ = ["BulkEditDialog"]
