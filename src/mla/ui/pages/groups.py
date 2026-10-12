from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QHBoxLayout, QInputDialog, QLineEdit, QListWidget, QListWidgetItem,
    QSplitter, QStackedLayout, QVBoxLayout, QWidget,
)

from mla.core.enums import CatalogStatus, Marketplace
from mla.core.models import ProductGroup
from mla.persistence.repositories import ProductQuery
from mla.ui.icons import icon
from mla.ui.pages.base import Page
from mla.ui.theme import T
from mla.ui.widgets.common import (
    EmptyState, Panel, button, confirm, icon_button, inform, label, show_toast,
)

ROLE_ID = Qt.ItemDataRole.UserRole


class ProductPicker(QDialog):
    """Multi-select products to add to a group."""

    def __init__(self, ctx, exclude: set[int], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Adicionar produtos ao grupo")
        self.resize(560, 600)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar produtos")
        self.search.addAction(icon("search", T.text_3, 16), QLineEdit.ActionPosition.LeadingPosition)
        layout.addWidget(self.search)
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        layout.addWidget(self.list, 1)
        self.ctx, self.exclude = ctx, exclude
        self.search.textChanged.connect(self._fill)
        foot = QHBoxLayout()
        self.count = label("", role="hint")
        foot.addWidget(self.count, 1)
        foot.addWidget(button("Cancelar", "ghost", None, self.reject))
        foot.addWidget(button("Adicionar selecionados", "primary", "plus", self.accept))
        layout.addLayout(foot)
        self.list.itemSelectionChanged.connect(
            lambda: self.count.setText(f"{len(self.list.selectedItems())} selecionado(s)"))
        self._fill()

    def _fill(self) -> None:
        self.list.clear()
        for summary in self.ctx.catalog.search(ProductQuery(text=self.search.text(), order_by="internal_name",
                                                            descending=False)):
            if summary.id in self.exclude:
                continue
            item = QListWidgetItem(f"{summary.internal_name}    {summary.sku}  ·  {summary.status.label}")
            item.setData(ROLE_ID, summary.id)
            self.list.addItem(item)

    def selected_ids(self) -> list[int]:
        return [item.data(ROLE_ID) for item in self.list.selectedItems()]


class GroupsPage(Page):
    key = "groups"
    title = "Grupos"
    subtitle = "Organize produtos em coleções e execute todos de uma vez."

    def __init__(self, ctx, navigate, parent=None):
        super().__init__(ctx, navigate, parent)
        self.header.add_action(button("Novo grupo", "primary", "plus", self.new_group))
        self._current: ProductGroup | None = None

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setHandleWidth(16)
        split.setChildrenCollapsible(False)
        self.group_list = QListWidget()
        self.group_list.setMinimumWidth(240)
        self.group_list.setMaximumWidth(340)
        self.group_list.currentItemChanged.connect(self._on_group_selected)
        split.addWidget(self.group_list)

        detail = QWidget()
        self.detail_stack = QStackedLayout(detail)
        self.empty = EmptyState("layers", "Nenhum grupo ainda",
                                "Crie grupos como Produtos 3D, Acessórios ou Campanha de Natal. "
                                "Um produto pode participar de vários grupos.",
                                button("Novo grupo", "primary", "plus", self.new_group))
        self.detail_stack.addWidget(self.empty)
        self.detail_stack.addWidget(self._build_detail())
        split.addWidget(detail)
        split.setStretchFactor(1, 1)
        self.root.addWidget(split, 1)

    def _build_detail(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        info = Panel()
        head = QHBoxLayout()
        self.name_label = label("", object_name="sectionTitle")
        head.addWidget(self.name_label, 1)
        head.addWidget(icon_button("pencil", "Renomear grupo", self._rename))
        head.addWidget(icon_button("trash-2", "Excluir grupo", self._delete, T.danger))
        info.body.addLayout(head)
        self.description = QLineEdit()
        self.description.setPlaceholderText("Descrição opcional do grupo")
        self.description.editingFinished.connect(self._save_meta)
        info.add(self.description)
        markets = QHBoxLayout()
        markets.addWidget(label("Publicar em:", role="muted"))
        self.market_checks: dict[Marketplace, QCheckBox] = {}
        for marketplace in (Marketplace.MERCADO_LIVRE, Marketplace.SHOPEE, Marketplace.SIMULATED):
            check = QCheckBox(marketplace.label)
            check.toggled.connect(self._save_meta)
            self.market_checks[marketplace] = check
            markets.addWidget(check)
        markets.addStretch(1)
        info.body.addLayout(markets)
        layout.addWidget(info)

        products = Panel("Produtos do grupo")
        self.products_count = label("", role="hint")
        products.header.addWidget(self.products_count)
        tools = QHBoxLayout()
        tools.addWidget(button("Adicionar produtos", "secondary", "plus", self._add_products))
        tools.addWidget(icon_button("arrow-up", "Mover para cima", lambda: self._move(-1)))
        tools.addWidget(icon_button("arrow-down", "Mover para baixo", lambda: self._move(1)))
        tools.addWidget(button("Remover do grupo", "ghost", "x", self._remove_products))
        tools.addStretch(1)
        tools.addWidget(button("Validar", "secondary", "list-checks", self._validate))
        tools.addWidget(button("Executar grupo", "primary", "play", self._run))
        products.body.addLayout(tools)
        self.items = QListWidget()
        self.items.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.items.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.items.model().rowsMoved.connect(self._persist_order)
        self.items.itemDoubleClicked.connect(
            lambda item: self.navigate("products", product_id=item.data(ROLE_ID)))
        products.add(self.items, 1)
        self.validation = label("", role="hint", wrap=True)
        products.add(self.validation)
        layout.addWidget(products, 1)
        return page

    # ------------------------------------------------------------------ data
    def refresh(self) -> None:
        current_id = self._current.id if self._current else None
        self.group_list.blockSignals(True)
        self.group_list.clear()
        for group in self.ctx.groups.list():
            item = QListWidgetItem(icon("layers", T.text_3, 16), f"{group.name}")
            item.setData(ROLE_ID, group.id)
            item.setToolTip(f"{len(group.product_ids)} produto(s)")
            self.group_list.addItem(item)
            if group.id == current_id:
                self.group_list.setCurrentItem(item)
        self.group_list.blockSignals(False)
        if self.group_list.count() and self.group_list.currentItem() is None:
            self.group_list.setCurrentRow(0)
        self._load_current()

    def open_with(self, new: bool = False, product_ids: list[int] | None = None, **_):
        if new:
            QTimer.singleShot(0, lambda: self.new_group(product_ids or []))

    def _on_group_selected(self, current, _previous) -> None:
        self._load_current()

    def _load_current(self) -> None:
        item = self.group_list.currentItem()
        self._current = self.ctx.groups.get(item.data(ROLE_ID)) if item else None
        if self._current is None:
            self.detail_stack.setCurrentIndex(0)
            return
        self.detail_stack.setCurrentIndex(1)
        group = self._current
        self.name_label.setText(group.name)
        self.description.setText(group.description)
        for marketplace, check in self.market_checks.items():
            check.blockSignals(True)
            check.setChecked(marketplace in group.marketplaces)
            check.blockSignals(False)
        self.items.clear()
        for position, pid in enumerate(group.product_ids, start=1):
            product = self.ctx.catalog.get(pid)
            if product is None:
                continue
            item = QListWidgetItem(f"{position}.  {product.internal_name}    {product.sku}")
            item.setData(ROLE_ID, pid)
            item.setToolTip(f"Status do cadastro: {product.status.label}")
            if product.status is not CatalogStatus.READY:
                item.setForeground(QColor(T.warning))
                item.setText(item.text() + f"    ({product.status.label.lower()})")
            self.items.addItem(item)
        n = len(group.product_ids)
        self.products_count.setText(f"{n} produto" + ("s" if n != 1 else ""))
        self.validation.setText("")

    # ------------------------------------------------------------------ actions
    def new_group(self, product_ids: list[int] | None = None) -> None:
        name, ok = QInputDialog.getText(self, "Novo grupo", "Nome do grupo:")
        if not ok or not name.strip():
            return
        try:
            group = self.ctx.groups.save(ProductGroup(name=name, product_ids=list(product_ids or [])))
        except ValueError as exc:
            inform(self, "Não foi possível criar", str(exc), error=True)
            return
        self._current = group
        self.refresh()
        show_toast(self, f"Grupo criado: {group.name}", "success")

    def _rename(self) -> None:
        if not self._current:
            return
        name, ok = QInputDialog.getText(self, "Renomear grupo", "Novo nome:", text=self._current.name)
        if ok and name.strip():
            self._current.name = name
            try:
                self.ctx.groups.save(self._current)
            except ValueError as exc:
                inform(self, "Não foi possível renomear", str(exc), error=True)
            self.refresh()

    def _delete(self) -> None:
        if self._current and confirm(self, "Excluir grupo", f"Excluir o grupo {self._current.name}? "
                                     "Os produtos continuam no catálogo.", "Excluir grupo", danger=True):
            self.ctx.groups.delete(self._current.id)
            self._current = None
            self.refresh()

    def _save_meta(self, *_args) -> None:
        if not self._current:
            return
        self._current.description = self.description.text().strip()
        self._current.marketplaces = [m for m, c in self.market_checks.items() if c.isChecked()]
        self.ctx.groups.save(self._current)

    def _add_products(self) -> None:
        if not self._current:
            return
        picker = ProductPicker(self.ctx, set(self._current.product_ids), self)
        if picker.exec() and picker.selected_ids():
            self.ctx.groups.add_products(self._current.id, picker.selected_ids())
            self._load_current()

    def _selected_product_ids(self) -> list[int]:
        return [item.data(ROLE_ID) for item in self.items.selectedItems()]

    def _remove_products(self) -> None:
        ids = self._selected_product_ids()
        if self._current and ids:
            self.ctx.groups.remove_products(self._current.id, ids)
            self._load_current()

    def _move(self, offset: int) -> None:
        ids = self._selected_product_ids()
        if not self._current or len(ids) != 1:
            return
        group = self.ctx.groups.move(self._current.id, ids[0], offset)
        self._load_current()
        row = group.product_ids.index(ids[0])
        self.items.setCurrentRow(row)

    def _persist_order(self, *_args) -> None:
        if not self._current:
            return
        self._current.product_ids = [self.items.item(r).data(ROLE_ID) for r in range(self.items.count())]
        self.ctx.groups.save(self._current)
        QTimer.singleShot(0, self._load_current)

    def _validate(self) -> bool:
        if not self._current:
            return False
        result = self.ctx.groups.validate(self._current.id)
        if 0 in result.blocked:
            self.validation.setText(result.blocked[0][0])
            self.validation.setStyleSheet(f"color: {T.warning};")
            return False
        if not result.blocked:
            self.validation.setText(f"Todos os {len(result.ready)} produtos estão prontos para os marketplaces escolhidos.")
            self.validation.setStyleSheet(f"color: {T.success};")
            return bool(result.ready)
        lines = []
        for pid, messages in list(result.blocked.items())[:6]:
            product = self.ctx.catalog.get(pid)
            lines.append(f"{product.internal_name if product else pid}: {messages[0]}")
        extra = len(result.blocked) - 6
        self.validation.setText(f"{len(result.ready)} prontos, {len(result.blocked)} com pendências:\n"
                                + "\n".join(lines) + (f"\n… e mais {extra}" if extra > 0 else ""))
        self.validation.setStyleSheet(f"color: {T.warning};")
        return False

    def _run(self) -> None:
        if not self._current:
            return
        if not self._current.marketplaces:
            self._validate()
            return
        self.navigate("automations", run_group=self._current.id)
