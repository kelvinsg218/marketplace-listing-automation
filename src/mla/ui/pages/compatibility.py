"""Compatibilidades: which vehicles, devices or equipment each product fits.

Nothing here is inferred. Every entry has a source; client data starts confirmed, anything else starts
unverified until the user confirms it, and rejected entries are kept (not deleted) so they are not
re-imported as new facts.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QGridLayout, QHBoxLayout, QHeaderView, QLineEdit, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from mla.core.enums import DataSource, Verification
from mla.core.models import Compatibility
from mla.services.compatibility import CompatibilityError, default_verification
from mla.ui.pages.base import Page
from mla.ui.widgets.common import (
    Callout, EmptyState, StatusDelegate, button, confirm, inform, label, plural, show_toast,
)

PAGE_SIZE = 500
COLUMNS = ["Produto", "Marca", "Modelo", "Versão", "Anos", "Referência", "Origem", "Verificação"]
SOURCES = [s for s in DataSource if s is not DataSource.AI]  # AI suggestions never become compatibilities here


def compat_table(columns: list[str] = COLUMNS) -> QTableWidget:
    table = QTableWidget(0, len(columns))
    table.setHorizontalHeaderLabels(columns)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(36)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    table.setShowGrid(False)
    table.setWordWrap(False)
    header = table.horizontalHeader()
    header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    header.setHighlightSections(False)
    table.setItemDelegateForColumn(len(columns) - 1, StatusDelegate(table, Verification))
    return table


def fill_compat_row(table: QTableWidget, row: int, c: Compatibility, with_product: bool = True) -> None:
    values = ([f"{c.sku}  {c.product_name}"] if with_product else []) + [
        c.brand, c.model, c.version, c.years(), c.reference_code,
        c.source.label + (f": {c.source_detail}" if c.source_detail else "")]
    for col, text in enumerate(values):
        item = QTableWidgetItem(text)
        item.setToolTip(text if len(text) > 30 else (c.notes or ""))
        table.setItem(row, col, item)
    status = QTableWidgetItem("")
    status.setData(Qt.ItemDataRole.UserRole, c.verification.value)
    table.setItem(row, len(values), status)


class CompatibilityDialog(QDialog):
    """Create or edit one compatibility. `product_id=None` lets the user pick the product by SKU."""

    def __init__(self, ctx, item: Compatibility | None = None, product_id: int | None = None, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.item = item or Compatibility(product_id, "", source=DataSource.CLIENT,
                                          verification=Verification.CONFIRMED)
        self.fixed_product = product_id is not None or item is not None
        self.setWindowTitle("Compatibilidade")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(12)
        layout.addWidget(label("Editar compatibilidade" if item and item.id else "Nova compatibilidade",
                               object_name="sectionTitle"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        self.sku = QLineEdit(item.sku if item else "")
        self.sku.setPlaceholderText("SKU do produto do catálogo")
        self.sku.setEnabled(not self.fixed_product)
        self.brand = QLineEdit(self.item.brand)
        self.brand.setPlaceholderText("Ex.: Fiat, Samsung, Sony")
        self.model = QLineEdit(self.item.model)
        self.model.setPlaceholderText("Ex.: Uno, Galaxy S23, PlayStation 5")
        self.version = QLineEdit(self.item.version)
        self.version.setPlaceholderText("Ex.: 1.0 Fire, Ultra, Slim")
        self.year_from, self.year_to = QSpinBox(), QSpinBox()
        for spin, value in ((self.year_from, self.item.year_from), (self.year_to, self.item.year_to)):
            spin.setRange(1899, 2100)
            spin.setSpecialValueText("—")
            spin.setValue(value or 1899)
        self.reference = QLineEdit(self.item.reference_code)
        self.reference.setPlaceholderText("Código original/OEM ou do fabricante do equipamento")
        self.notes = QLineEdit(self.item.notes)
        self.source = QComboBox()
        for source in SOURCES:
            self.source.addItem(source.label, source)
        self.source.setCurrentIndex(max(0, self.source.findData(self.item.source)))
        self.source_detail = QLineEdit(self.item.source_detail)
        self.source_detail.setPlaceholderText("Ex.: tabela do fornecedor, manual, site do fabricante")
        self.verification = QComboBox()
        for v in Verification:
            self.verification.addItem(v.label, v)
        self.verification.setCurrentIndex(self.verification.findData(self.item.verification))
        if not (item and item.id):
            self.source.currentIndexChanged.connect(
                lambda: self.verification.setCurrentIndex(self.verification.findData(
                    default_verification(DataSource(self.source.currentData())))))
        rows = [("Produto (SKU)", self.sku), ("Marca compatível", self.brand), ("Modelo compatível *", self.model),
                ("Versão", self.version), ("Ano inicial", self.year_from), ("Ano final", self.year_to),
                ("Código de referência", self.reference), ("Observações", self.notes),
                ("Fonte da informação", self.source), ("Detalhe da fonte", self.source_detail),
                ("Verificação", self.verification)]
        for index, (caption, widget) in enumerate(rows):
            r, c = divmod(index, 2)
            box = QVBoxLayout()
            box.setSpacing(4)
            box.addWidget(label(caption, role="muted"))
            box.addWidget(widget)
            grid.addLayout(box, r, c)
        layout.addLayout(grid)
        layout.addWidget(Callout("Cadastre só o que o cliente, o fabricante ou uma fonte identificada informa. "
                                 "Fontes externas ficam como não verificadas até você confirmar."))
        foot = QHBoxLayout()
        foot.addStretch(1)
        foot.addWidget(button("Cancelar", "ghost", None, self.reject))
        foot.addWidget(button("Salvar", "primary", "check", self._accept))
        layout.addLayout(foot)

    def collect(self) -> Compatibility:
        c = self.item
        c.brand, c.model, c.version = self.brand.text(), self.model.text(), self.version.text()
        c.year_from = self.year_from.value() if self.year_from.value() > 1899 else None
        c.year_to = self.year_to.value() if self.year_to.value() > 1899 else None
        c.reference_code, c.notes = self.reference.text(), self.notes.text()
        c.source, c.source_detail = DataSource(self.source.currentData()), self.source_detail.text()
        c.verification = Verification(self.verification.currentData())
        if not self.fixed_product:
            pid = self.ctx.products.id_for_sku(self.sku.text().strip()) if self.sku.text().strip() else None
            c.product_id = pid
        return c

    def _accept(self) -> None:
        c = self.collect()
        if c.product_id is None and not self.fixed_product:
            inform(self, "Produto não encontrado", "Informe o SKU de um produto do catálogo.", error=True)
            return
        try:
            self.ctx.compatibility.validate(c)
        except CompatibilityError as exc:
            inform(self, "Confira os dados", str(exc), error=True)
            return
        self.accept()


class CompatibilityPage(Page):
    key = "compatibility"
    title = "Compatibilidades"

    def __init__(self, ctx, navigate, parent=None):
        super().__init__(ctx, navigate, parent)
        self.header.add_action(button("Importar compatibilidades…", "secondary", "file-up",
                                      lambda: self.navigate("imports", wizard=True, target="compatibility")))
        self.header.add_action(button("Nova compatibilidade", "primary", "plus", self._new))
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar marca, modelo, versão, referência ou SKU")
        self.search.setClearButtonEnabled(True)
        self._debounce = QTimer(self, singleShot=True, interval=220, timeout=self.refresh)
        self.search.textChanged.connect(lambda _t: self._debounce.start())
        bar.addWidget(self.search, 1)
        self.verification = QComboBox()
        self.verification.addItem("Toda verificação", None)
        for v in Verification:
            self.verification.addItem(v.label, v)
        self.verification.currentIndexChanged.connect(self.refresh)
        bar.addWidget(self.verification)
        self.source = QComboBox()
        self.source.addItem("Toda origem", None)
        for s in SOURCES:
            self.source.addItem(s.label, s)
        self.source.currentIndexChanged.connect(self.refresh)
        bar.addWidget(self.source)
        self.root.addLayout(bar)
        self.root.addWidget(Callout("O MLA não cria compatibilidades sozinho. Dados do cliente entram como "
                                    "confirmados; fabricante e fontes externas entram como não verificados."))
        actions = QHBoxLayout()
        self.count_label = label("", role="hint")
        actions.addWidget(self.count_label, 1)
        self.edit_btn = button("Editar", "ghost", "pencil", self._edit)
        self.confirm_btn = button("Confirmar", "secondary", "badge-check",
                                  lambda: self._verify(Verification.CONFIRMED))
        self.unverify_btn = button("Marcar não verificada", "ghost", "rotate-ccw",
                                   lambda: self._verify(Verification.UNVERIFIED))
        self.reject_btn = button("Rejeitar", "ghost", "ban", lambda: self._verify(Verification.REJECTED))
        self.delete_btn = button("Excluir", "danger", "trash-2", self._delete)
        for b in (self.edit_btn, self.confirm_btn, self.unverify_btn, self.reject_btn, self.delete_btn):
            actions.addWidget(b)
        self.root.addLayout(actions)
        self.table = compat_table()
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col, width in ((1, 120), (2, 150), (3, 110), (4, 100), (5, 120), (6, 170), (7, 140)):
            h.resizeSection(col, width)
        self.table.itemSelectionChanged.connect(self._sync)
        self.table.doubleClicked.connect(lambda _i: self._edit())
        self.root.addWidget(self.table, 1)
        self.empty = EmptyState("puzzle", "Nenhuma compatibilidade",
                                "Importe a tabela de aplicação do cliente (SKU, marca, modelo, versão, anos) ou "
                                "cadastre manualmente.",
                                button("Importar compatibilidades", "primary", "file-up",
                                       lambda: self.navigate("imports", wizard=True, target="compatibility")))
        self.root.addWidget(self.empty, 1)
        more = QHBoxLayout()
        more.addStretch(1)
        self.more_btn = button("Carregar mais", "ghost", None, lambda: self._load(append=True))
        more.addWidget(self.more_btn)
        self.root.addLayout(more)
        self._items: list[Compatibility] = []
        self._total = 0

    def refresh(self) -> None:
        self._load(append=False)
        counts = self.ctx.compatibility.repo.counts_by_verification()
        self.header.set_subtitle(f"{plural(sum(counts.values()), 'compatibilidade', 'compatibilidades')}: "
                                 f"{counts[Verification.CONFIRMED]} confirmada(s), "
                                 f"{counts[Verification.UNVERIFIED]} não verificada(s)")

    def _filters(self):
        return self.search.text(), self.verification.currentData(), self.source.currentData()

    def _load(self, append: bool) -> None:
        text, verification, source = self._filters()
        offset = len(self._items) if append else 0
        page = self.ctx.compatibility.search(text, verification, source, limit=PAGE_SIZE, offset=offset)
        self._items = (self._items + page) if append else page
        self._total = self.ctx.compatibility.count(text, verification, source)
        self.table.setRowCount(len(self._items))
        for r in range(offset, len(self._items)):
            fill_compat_row(self.table, r, self._items[r])
        filtered = bool(text or verification or source)
        self.table.setVisible(bool(self._items) or filtered)
        self.empty.setVisible(not self._items and not filtered)
        self.more_btn.setVisible(len(self._items) < self._total)
        self._sync()

    def _selected(self) -> list[Compatibility]:
        rows = {i.row() for i in self.table.selectionModel().selectedRows()}
        return [self._items[r] for r in sorted(rows) if r < len(self._items)]

    def _sync(self) -> None:
        items = self._selected()
        self.edit_btn.setVisible(len(items) == 1)
        for b in (self.confirm_btn, self.unverify_btn, self.reject_btn, self.delete_btn):
            b.setVisible(bool(items))
        self.count_label.setText(plural(len(items), "selecionada", "selecionadas") if items else
                                 f"{len(self._items)} de {self._total} exibidas" if self._total else "")

    def _new(self) -> None:
        dialog = CompatibilityDialog(self.ctx, parent=self)
        if dialog.exec():
            self._save(dialog.collect())

    def _edit(self) -> None:
        items = self._selected()
        if len(items) != 1:
            return
        dialog = CompatibilityDialog(self.ctx, items[0], parent=self)
        if dialog.exec():
            self._save(dialog.collect())

    def _save(self, item: Compatibility) -> None:
        try:
            self.ctx.compatibility.save(item)
        except CompatibilityError as exc:
            inform(self, "Não foi possível salvar", str(exc), error=True)
            return
        self.refresh()
        show_toast(self, "Compatibilidade salva", "success")

    def _verify(self, verification: Verification) -> None:
        items = self._selected()
        count = self.ctx.compatibility.set_verification([c.id for c in items], verification)
        self.refresh()
        show_toast(self, f"{count} marcada(s) como {verification.label.lower()}")

    def _delete(self) -> None:
        items = self._selected()
        if not items or not confirm(self, "Excluir compatibilidades", f"Excluir {plural(len(items), 'compatibilidade', 'compatibilidades')}? "
                                    "Para guardar o registro de que uma informação está errada, use Rejeitar.",
                                    "Excluir", danger=True):
            return
        self.ctx.compatibility.delete([c.id for c in items])
        self.refresh()


__all__ = ["CompatibilityDialog", "CompatibilityPage", "compat_table", "fill_compat_row"]
