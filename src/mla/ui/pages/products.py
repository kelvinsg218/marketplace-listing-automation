from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLineEdit, QMenu, QStackedLayout,
    QStyledItemDelegate, QTableView, QWidget,
)

from mla.core.enums import CatalogStatus, CommercialStatus, Marketplace
from mla.core.models import ProductSummary
from mla.core.units import format_money
from mla.persistence.repositories import ProductQuery
from mla.ui.icons import icon
from mla.ui.pages.base import Page
from mla.ui.theme import T, tone_for
from mla.ui.widgets.common import (
    EmptyState, button, confirm, format_when, label, paint_chip, plural, show_toast, thumbnail,
)

COLUMNS = [("Produto", "internal_name"), ("Status", "status"), ("Preço", "price_cents"),
           ("Estoque", "stock"), ("Mídia", None), ("Compat.", None), ("Atualizado", "updated_at")]
ROW_HEIGHT = 56
PAGE_SIZE = 200  # rows loaded per step; more are fetched as the user scrolls
MP_SHORT = {Marketplace.MERCADO_LIVRE: "ML", Marketplace.SHOPEE: "Shopee", Marketplace.SIMULATED: "Simulado"}


class ProductTableModel(QAbstractTableModel):
    sortRequested = Signal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: list[ProductSummary] = []
        self.total = 0
        self._loader = None

    def set_rows(self, rows: list[ProductSummary]) -> None:
        self.beginResetModel()
        self.rows, self.total, self._loader = rows, len(rows), None
        self.endResetModel()

    def load(self, loader, total: int) -> None:
        """Incremental loading: `loader(offset, limit)` returns the next rows of the current query."""
        self.beginResetModel()
        self._loader, self.total = loader, total
        self.rows = loader(0, PAGE_SIZE) if total else []
        self.endResetModel()

    def canFetchMore(self, parent=QModelIndex()) -> bool:
        return not parent.isValid() and self._loader is not None and len(self.rows) < self.total

    def fetchMore(self, parent=QModelIndex()) -> None:
        if not self.canFetchMore(parent):
            return
        more = self._loader(len(self.rows), PAGE_SIZE)
        if not more:
            self.total = len(self.rows)
            return
        start = len(self.rows)
        self.beginInsertRows(QModelIndex(), start, start + len(more) - 1)
        self.rows += more
        self.endInsertRows()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section][0]
        if role == Qt.ItemDataRole.TextAlignmentRole and section in (2, 3):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.UserRole:
            return row
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return row.internal_name
            if col == 1:
                return row.status.label
            if col == 2:
                return format_money(row.price_cents) or "—"
            if col == 3:
                return str(row.stock)
            if col == 4:
                text = plural(row.image_count, "imagem", "imagens") if row.image_count else "Sem imagem"
                return text + (f", {plural(row.missing_media, 'pendente', 'pendentes')}" if row.missing_media else "")
            if col == 5:
                return str(row.compat_count) if row.compat_count else "—"
            if col == 6:
                return format_when(row.updated_at)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (2, 3):
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ForegroundRole and col == 4 and (row.missing_media or not row.image_count):
            return QColor(T.warning)
        if role == Qt.ItemDataRole.ForegroundRole and col in (4, 5, 6):
            return QColor(T.text_2)
        if role == Qt.ItemDataRole.AccessibleTextRole:
            return f"{row.internal_name}, SKU {row.sku}, {row.status.label}"
        return None

    def sort(self, column: int, order=Qt.SortOrder.AscendingOrder) -> None:
        field = COLUMNS[column][1]
        if field:
            self.sortRequested.emit(field, order == Qt.SortOrder.DescendingOrder)


class ProductDelegate(QStyledItemDelegate):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx

    def paint(self, painter: QPainter, option, index) -> None:
        row: ProductSummary = index.data(Qt.ItemDataRole.UserRole)
        col = index.column()
        if col not in (0, 1):
            super().paint(painter, option, index)
            return
        self.initStyleOption(option, index)
        option.text = ""
        option.widget.style().drawControl(option.widget.style().ControlElement.CE_ItemViewItem, option, painter,
                                          option.widget)
        rect = option.rect.adjusted(10, 0, -8, 0)
        if col == 1:
            fg, bg = tone_for(row.status)
            paint_chip(painter, rect, row.status.label, fg, bg, option.font)
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        thumb_rect = QRect(rect.left(), rect.center().y() - 20, 40, 40)
        pm = thumbnail(self.ctx.images.path_for(row.main_image), 40) if row.main_image else None
        if pm is not None and not pm.isNull():
            painter.setClipRect(thumb_rect)
            painter.drawPixmap(thumb_rect, pm)
            painter.setClipping(False)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(T.raised))
            painter.drawRoundedRect(thumb_rect, 6, 6)
            icon("package", T.text_3, 18).paint(painter, thumb_rect.adjusted(11, 11, -11, -11))
        text_rect = rect.adjusted(52, 9, 0, -9)
        name_font = QFont(option.font)
        name_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(name_font)
        painter.setPen(QColor(T.text))
        fm = painter.fontMetrics()
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                         fm.elidedText(row.internal_name, Qt.TextElideMode.ElideRight, text_rect.width()))
        sub_font = QFont(option.font)
        sub_font.setPixelSize(12)
        painter.setFont(sub_font)
        painter.setPen(QColor(T.text_3))
        sub = f"{row.sku}   {row.title}" if row.title else row.sku
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft,
                         painter.fontMetrics().elidedText(sub, Qt.TextElideMode.ElideRight, text_rect.width()))
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        return QSize(super().sizeHint(option, index).width(), ROW_HEIGHT)


class ProductsPage(Page):
    key = "products"
    title = "Catálogo mestre"

    def __init__(self, ctx, navigate, parent=None):
        super().__init__(ctx, navigate, parent)
        self._query = ProductQuery()
        io_menu = QMenu(self)
        io_menu.addAction("Importar base de produtos…", lambda: self.navigate("imports", wizard=True))
        io_menu.addSeparator()
        io_menu.addAction("Exportar CSV…", lambda: self._export("csv"))
        io_menu.addAction("Exportar JSON (completo, com variações)…", lambda: self._export("json"))
        io_btn = button("Importar e exportar", "secondary", "download")
        io_btn.setMenu(io_menu)
        self.header.add_action(io_btn)
        self.header.add_action(button("Novo produto", "primary", "plus", self.new_product))

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar por nome, SKU (inclusive de variação), GTIN, código do fabricante, "
                                       "marca ou fornecedor")
        self.search.addAction(icon("search", T.text_3, 16), QLineEdit.ActionPosition.LeadingPosition)
        self.search.setClearButtonEnabled(True)
        self._debounce = QTimer(self, singleShot=True, interval=220, timeout=self.refresh)
        self.search.textChanged.connect(lambda _t: self._debounce.start())
        bar.addWidget(self.search, 1)
        self.status_filter = QComboBox()
        self.status_filter.addItem("Todos os status", None)
        for status in CatalogStatus:
            self.status_filter.addItem(status.label, status)
        self.status_filter.currentIndexChanged.connect(self.refresh)
        bar.addWidget(self.status_filter)
        self.commercial_filter = QComboBox()
        self.commercial_filter.addItem("Toda situação comercial", None)
        for status in CommercialStatus:
            self.commercial_filter.addItem(status.label, status)
        self.commercial_filter.currentIndexChanged.connect(self.refresh)
        bar.addWidget(self.commercial_filter)
        self.missing_filter = QCheckBox("Mídia pendente")
        self.missing_filter.setToolTip("Produtos com imagens ou arquivos citados na importação e não encontrados")
        self.missing_filter.toggled.connect(self.refresh)
        bar.addWidget(self.missing_filter)
        self.group_filter = QComboBox()
        self.group_filter.currentIndexChanged.connect(self.refresh)
        bar.addWidget(self.group_filter)
        self.root.addLayout(bar)

        selection_bar = QHBoxLayout()
        self.count_label = label("", role="hint")
        selection_bar.addWidget(self.count_label, 1)
        self.prepare_btn = button("Preparar anúncios", "primary", "tag", self._prepare_listings)
        self.run_btn = button("Executar", "secondary", "play", self._run_selected)
        self.edit_btn = button("Editar", "ghost", "pencil", self._edit_selected)
        self.dup_btn = button("Duplicar", "ghost", "copy", self._duplicate_selected)
        self.group_btn = button("Adicionar ao grupo", "ghost", "layers", self._add_to_group)
        self.del_btn = button("Excluir", "danger", "trash-2", self._delete_selected)
        for b in (self.prepare_btn, self.run_btn, self.edit_btn, self.dup_btn, self.group_btn, self.del_btn):
            selection_bar.addWidget(b)
        self.root.addLayout(selection_bar)

        self.model = ProductTableModel(self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setItemDelegate(ProductDelegate(ctx, self.table))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSortIndicator(6, Qt.SortOrder.DescendingOrder)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setMouseTracking(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setHighlightSections(False)
        for col, width in ((1, 130), (2, 100), (3, 70), (4, 150), (5, 64), (6, 110)):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            header.resizeSection(col, width)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.table.doubleClicked.connect(lambda _i: self._edit_selected())
        self.table.selectionModel().selectionChanged.connect(self._sync_actions)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)

        self.empty = EmptyState("package", "Nenhum produto cadastrado",
                                "Cadastre o primeiro produto ou importe a base da empresa (planilha, XML, JSON, PDF "
                                "ou ZIP com fotos) pela Central de Importações.",
                                button("Importar base de produtos", "primary", "file-up",
                                       lambda: self.navigate("imports", wizard=True)))
        self.no_results = EmptyState("search", "Nada encontrado", "Ajuste a busca ou os filtros.")
        holder = QWidget()
        self.stack = QStackedLayout(holder)
        self.stack.addWidget(self.table)
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self.no_results)
        self.root.addWidget(holder, 1)

        QShortcut(QKeySequence.StandardKey.Delete, self.table, activated=self._delete_selected)
        QShortcut(QKeySequence("Ctrl+D"), self, activated=self._duplicate_selected)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.search.setFocus)
        self.model.sortRequested.connect(self._sort)  # connect last: enabling sorting emits sort() immediately
        self._sync_actions()

    # ------------------------------------------------------------------ data
    def refresh(self) -> None:
        current_group = self.group_filter.currentData()
        self.group_filter.blockSignals(True)
        self.group_filter.clear()
        self.group_filter.addItem("Todos os grupos", None)
        for group in self.ctx.groups.list():
            self.group_filter.addItem(group.name, group.id)
        index = self.group_filter.findData(current_group)
        self.group_filter.setCurrentIndex(max(0, index))
        self.group_filter.blockSignals(False)
        self._query.text = self.search.text()
        self._query.status = self.status_filter.currentData()
        self._query.group_id = self.group_filter.currentData()
        self._query.commercial_status = self.commercial_filter.currentData()
        self._query.missing_media_only = self.missing_filter.isChecked()
        selected = set(self.selected_ids())
        query = replace(self._query)
        total = self.ctx.products.count(query)
        self.model.load(lambda offset, limit: self.ctx.catalog.search(replace(query, offset=offset, limit=limit)),
                        total)
        for r, summary in enumerate(self.model.rows):
            if summary.id in selected:
                self.table.selectRow(r)
        filtered = bool(query.text or query.status or query.group_id or query.commercial_status
                        or query.missing_media_only)
        self.stack.setCurrentIndex(0 if total else (2 if filtered else 1))
        total = self.ctx.products.count_by_status()
        self.header.set_subtitle(f"{plural(sum(total.values()), 'cadastrado', 'cadastrados')}, "
                                 f"{plural(total[CatalogStatus.READY], 'pronto', 'prontos')} para anunciar")
        self._sync_actions()

    def open_with(self, new: bool = False, status: CatalogStatus | None = None, product_id: int | None = None, **_):
        if status is not None:
            self.status_filter.setCurrentIndex(self.status_filter.findData(status))
        if new:
            QTimer.singleShot(0, self.new_product)
        if product_id is not None:
            QTimer.singleShot(0, lambda: self.edit_product(product_id))

    def selected_ids(self) -> list[int]:
        model = self.table.selectionModel()
        if model is None:
            return []
        return [self.model.rows[i.row()].id for i in model.selectedRows() if i.row() < len(self.model.rows)]

    def _sync_actions(self, *_args) -> None:
        n = len(self.selected_ids())
        for b in (self.prepare_btn, self.run_btn, self.dup_btn, self.group_btn, self.del_btn):
            b.setVisible(n > 0)
        self.edit_btn.setVisible(n == 1)
        if n:
            self.count_label.setText(plural(n, "selecionado", "selecionados"))
        elif self.model.total:
            self.count_label.setText(f"{plural(self.model.total, 'produto encontrado', 'produtos encontrados')}. "
                                     "Selecione para preparar anúncios, duplicar ou excluir.")

    def _sort(self, field: str, descending: bool) -> None:
        self._query.order_by, self._query.descending = field, descending
        self.refresh()

    # ------------------------------------------------------------------ actions
    def new_product(self) -> None:
        from mla.ui.pages.product_editor import ProductEditor
        editor = ProductEditor(self.ctx, None, self)
        if editor.exec():
            self.refresh()
            show_toast(self, f"Produto salvo: {editor.product.internal_name}", "success")

    def edit_product(self, product_id: int) -> None:
        from mla.ui.pages.product_editor import ProductEditor
        product = self.ctx.catalog.get(product_id)
        if product is None:
            return
        editor = ProductEditor(self.ctx, product, self)
        if editor.exec():
            self.refresh()
            show_toast(self, "Alterações salvas", "success")

    def _edit_selected(self) -> None:
        ids = self.selected_ids()
        if len(ids) == 1:
            self.edit_product(ids[0])

    def _duplicate_selected(self) -> None:
        ids = self.selected_ids()
        for pid in ids:
            self.ctx.catalog.duplicate(pid)
        if ids:
            self.refresh()
            show_toast(self, f"{len(ids)} produto(s) duplicado(s); revise os SKUs das cópias", "success")

    def _delete_selected(self) -> None:
        ids = self.selected_ids()
        if not ids:
            return
        noun = "este produto" if len(ids) == 1 else f"estes {len(ids)} produtos"
        if not confirm(self, "Excluir produtos", f"Excluir {noun}? As imagens que só eles usam também serão "
                       "removidas. O histórico de execuções é mantido.", "Excluir", danger=True):
            return
        self.ctx.catalog.delete(ids)
        self.refresh()
        show_toast(self, f"{len(ids)} produto(s) excluído(s)")

    def _add_to_group(self) -> None:
        ids = self.selected_ids()
        groups = self.ctx.groups.list()
        menu = QMenu(self)
        for group in groups:
            menu.addAction(group.name, lambda _checked=False, g=group: self._do_add_to_group(g.id, g.name, ids))
        if groups:
            menu.addSeparator()
        menu.addAction("Novo grupo…", lambda: self.navigate("groups", new=True, product_ids=ids))
        menu.exec(self.group_btn.mapToGlobal(self.group_btn.rect().bottomLeft()))

    def _do_add_to_group(self, group_id: int, name: str, ids: list[int]) -> None:
        self.ctx.groups.add_products(group_id, ids)
        show_toast(self, f"{len(ids)} produto(s) adicionado(s) ao grupo {name}", "success")

    def _run_selected(self) -> None:
        ids = self.selected_ids()
        if ids:
            self.navigate("automations", run_products=ids)

    def _context_menu(self, pos) -> None:
        if not self.selected_ids():
            return
        menu = QMenu(self)
        if len(self.selected_ids()) == 1:
            menu.addAction(icon("pencil"), "Editar", self._edit_selected)
        menu.addAction(icon("tag"), "Preparar anúncios…", self._prepare_listings)
        menu.addAction(icon("play"), "Executar", self._run_selected)
        menu.addAction(icon("copy"), "Duplicar", self._duplicate_selected)
        menu.addAction(icon("layers"), "Adicionar ao grupo", self._add_to_group)
        menu.addAction(icon("download"), "Exportar selecionados (JSON)…",
                       lambda: self._export("json", self.selected_ids()))
        menu.addSeparator()
        menu.addAction(icon("trash-2", T.danger), "Excluir", self._delete_selected)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _prepare_listings(self) -> None:
        ids = self.selected_ids()
        if not ids:
            return
        from mla.ui.pages.listings import PrepareListingsDialog
        dialog = PrepareListingsDialog(self.ctx, ids, self)
        if dialog.exec() and dialog.result_info is not None:
            marketplace, account_id, result = dialog.result_info
            show_toast(self, result.summary(), "success" if result.created else "neutral")
            self.navigate("listings", marketplace=marketplace, account_id=account_id)

    def _export(self, kind: str, ids: list[int] | None = None) -> None:
        default = str(self.ctx.paths.exports / f"catalogo.{kind}")
        pattern = "Planilha CSV (*.csv)" if kind == "csv" else "Catálogo JSON (*.json)"
        path, _ = QFileDialog.getSaveFileName(self, "Exportar produtos", default, pattern)
        if not path:
            return
        service = self.ctx.import_export
        count = service.export_csv(Path(path), ids) if kind == "csv" else service.export_json(Path(path), ids)
        show_toast(self, f"{count} produto(s) exportado(s) com as imagens em {Path(path).stem}_imagens", "success")
