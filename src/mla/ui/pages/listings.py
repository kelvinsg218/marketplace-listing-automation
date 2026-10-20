"""Preparação de Anúncios: offers (product × marketplace × account) prepared from the master catalog.

A listing only stores what differs from the master product; the editor shows the inherited value as a
placeholder. Preparation states come from validating the effective content; only approved listings
can be sent to the automation queue, and only a confirmed publication marks one as published.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QLineEdit, QListWidget, QListWidgetItem,
    QPlainTextEdit, QStackedLayout, QStyledItemDelegate, QTableView, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from mla.automation.adapters import adapter_for
from mla.core.enums import ListingStatus, Marketplace
from mla.core.models import Listing, ListingRow
from mla.core.units import ParseError, format_money, parse_money_strict
from mla.core.validation import MARKETPLACE_RULES
from mla.services.listing_export import NOTICE, ListingExporter
from mla.services.listings import ListingError
from mla.ui.icons import icon, pixmap
from mla.ui.pages.base import Page
from mla.ui.theme import T, tone_for
from mla.ui.widgets.common import (
    Callout, EmptyState, StatusChip, button, clear_layout, confirm, inform, label, paint_chip, plural, show_toast,
    thumbnail,
)

MARKETPLACES = (Marketplace.MERCADO_LIVRE, Marketplace.SHOPEE, Marketplace.SIMULATED)
PAGE_SIZE = 200
ROW_HEIGHT = 56
FILTERS = [
    ("Todas as situações", None),
    ("Precisam de correção", [ListingStatus.DRAFT, ListingStatus.INCOMPLETE]),
    ("Prontos para revisão", [ListingStatus.READY]),
    ("Aprovados", [ListingStatus.APPROVED]),
    ("Na fila ou em execução", [ListingStatus.QUEUED, ListingStatus.RUNNING, ListingStatus.AWAITING_REVIEW]),
    ("Publicados confirmados", [ListingStatus.PUBLISHED]),
    ("Falha ou intervenção", [ListingStatus.FAILED, ListingStatus.NEEDS_ATTENTION, ListingStatus.CANCELLED]),
]
COLUMNS = ["Produto", "Conta", "Título do anúncio", "Preço", "Situação", "Pendências"]


def _account_combo(ctx, marketplace: Marketplace, combo: QComboBox, with_all: bool = False,
                   active_only: bool = True) -> None:
    current = combo.currentData()
    combo.blockSignals(True)
    combo.clear()
    if with_all:
        combo.addItem("Todas as contas", None)
    for account in ctx.accounts.list(marketplace, active_only=active_only):
        combo.addItem(account.label + ("" if account.is_active else " (desativada)"), account.id)
    index = combo.findData(current)
    combo.setCurrentIndex(index if index >= 0 else 0)
    combo.blockSignals(False)


# ---------------------------------------------------------------------------- prepare dialog
class PrepareListingsDialog(QDialog):
    """Choose marketplace + account and create one listing per selected product."""

    def __init__(self, ctx, product_ids: list[int], parent=None, marketplace: Marketplace | None = None):
        super().__init__(parent)
        self.ctx, self.product_ids = ctx, product_ids
        self.result_info = None
        self.setWindowTitle("Preparar anúncios")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(12)
        layout.addWidget(label("Preparar anúncios", object_name="sectionTitle"))
        layout.addWidget(label(f"{plural(len(product_ids), 'produto selecionado', 'produtos selecionados')}. "
                               "Cada um vira um anúncio na conta escolhida, usando os dados do catálogo mestre. "
                               "Título, preço, estoque e imagens podem ser ajustados por anúncio depois.",
                               role="muted", wrap=True))
        self.marketplace = QComboBox()
        for m in MARKETPLACES:
            self.marketplace.addItem(m.label, m)
        if marketplace is not None:
            self.marketplace.setCurrentIndex(self.marketplace.findData(marketplace))
        self.account = QComboBox()
        layout.addWidget(label("Marketplace", role="muted"))
        layout.addWidget(self.marketplace)
        layout.addWidget(label("Conta de destino", role="muted"))
        layout.addWidget(self.account)
        self.note = Callout()
        layout.addWidget(self.note)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button("Cancelar", "ghost", None, self.reject))
        self.ok = button("Preparar", "primary", "tag", self._prepare)
        row.addWidget(self.ok)
        layout.addLayout(row)
        self.marketplace.currentIndexChanged.connect(self._sync)
        self._sync()

    def _sync(self) -> None:
        marketplace = Marketplace(self.marketplace.currentData())
        _account_combo(self.ctx, marketplace, self.account)
        has_account = self.account.count() > 0
        self.ok.setEnabled(has_account)
        if not has_account:
            text = f"Nenhuma conta ativa do {marketplace.label}. Cadastre uma em Marketplaces."
        elif not adapter_for(marketplace).implemented:
            text = (f"A publicação automática no {marketplace.label} ainda não está disponível: os anúncios ficam "
                    "preparados e revisados, prontos para quando a integração for liberada.")
        else:
            text = "Nada é publicado agora. Depois de revisar e aprovar, envie os aprovados para a fila."
        self.note.set_text(text)

    def _prepare(self) -> None:
        marketplace = Marketplace(self.marketplace.currentData())
        try:
            result = self.ctx.listings.prepare(self.product_ids, marketplace, self.account.currentData())
        except ListingError as exc:
            inform(self, "Não foi possível preparar", str(exc), error=True)
            return
        self.result_info = (marketplace, self.account.currentData(), result)
        self.accept()


# ---------------------------------------------------------------------------- listing editor
class ListingEditor(QDialog):
    def __init__(self, ctx, listing: Listing, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.listing = listing
        self.product = ctx.products.get(listing.product_id)
        self.master = ctx.listings.payload(Listing(listing.product_id, listing.marketplace, listing.account_id,
                                                   listing.status), self.product)
        account = ctx.accounts.get(listing.account_id)
        self.editable = not (listing.status.in_execution or listing.status is ListingStatus.PUBLISHED)
        self.setWindowTitle(f"Anúncio de {self.product.internal_name}")
        self.resize(1080, 740)
        self.setMinimumSize(920, 620)
        self._loading = True

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 16)
        outer.setSpacing(12)
        head = QHBoxLayout()
        title = QVBoxLayout()
        title.setSpacing(2)
        title.addWidget(label(self.product.internal_name, object_name="pageTitle"))
        title.addWidget(label(f"SKU {self.product.sku}   {listing.marketplace.label}, conta "
                              f"{account.label if account else '?'}", role="muted"))
        head.addLayout(title, 1)
        self.chip = StatusChip(listing.status)
        head.addWidget(self.chip, 0, Qt.AlignmentFlag.AlignTop)
        outer.addLayout(head)
        if not self.editable:
            outer.addWidget(Callout(f"Anúncio {listing.status.label.lower()}: o conteúdo não pode ser alterado "
                                    "agora.", warn=True))
        outer.addWidget(label("Campos vazios usam o valor do catálogo mestre (mostrado em cinza).", role="hint"))

        body = QHBoxLayout()
        body.setSpacing(24)
        form = QVBoxLayout()
        form.setSpacing(10)
        self.title_edit = QLineEdit(listing.title)
        self.title_edit.setPlaceholderText(self.master.title or "Sem título no catálogo")
        self.title_counter = label("", role="hint")
        form.addWidget(label("Título do anúncio", role="muted"))
        form.addWidget(self.title_edit)
        form.addWidget(self.title_counter)
        self.description = QPlainTextEdit(listing.description)
        self.description.setPlaceholderText(self.master.description or "Sem descrição no catálogo")
        self.description.setMinimumHeight(150)
        form.addWidget(label("Descrição do anúncio", role="muted"))
        form.addWidget(self.description, 1)
        grid = QHBoxLayout()
        self.price = QLineEdit(format_money(listing.price_cents, symbol=False))
        self.price.setPlaceholderText(format_money(self.master.price_cents, symbol=False) or "0,00")
        self.stock = QLineEdit("" if listing.stock is None else str(listing.stock))
        self.stock.setPlaceholderText(str(self.master.stock))
        self.category_id = QLineEdit(listing.category_id)
        self.category_id.setPlaceholderText(self.master.category_id or "Escolhida no formulário")
        self.listing_type = QLineEdit(listing.listing_type)
        self.listing_type.setPlaceholderText(self.master.listing_type or "Padrão")
        for caption, widget in (("Preço (R$)", self.price), ("Estoque anunciado", self.stock),
                                ("Categoria no marketplace", self.category_id), ("Tipo de anúncio", self.listing_type)):
            box = QVBoxLayout()
            box.addWidget(label(caption, role="muted"))
            box.addWidget(widget)
            grid.addLayout(box)
        form.addLayout(grid)
        form.addWidget(label("Atributos exigidos pela categoria (Nome = valor)", role="muted"))
        self.attributes = QTableWidget(0, 2)
        self.attributes.setHorizontalHeaderLabels(["Atributo", "Valor"])
        self.attributes.verticalHeader().setVisible(False)
        self.attributes.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.attributes.setMaximumHeight(130)
        for key, value in listing.attributes.items():
            self._add_attribute(key, value)
        inherited = {k: v for k, v in self.master.attributes.items() if k not in listing.attributes}
        attr_row = QHBoxLayout()
        attr_row.addWidget(button("Adicionar atributo", "ghost", "plus", lambda: self._add_attribute()))
        attr_row.addWidget(label("Do catálogo: " + ", ".join(f"{k}={v}" for k, v in inherited.items())
                                 if inherited else "", role="hint"), 1)
        form.addWidget(self.attributes)
        form.addLayout(attr_row)
        self.notes = QLineEdit(listing.notes)
        self.notes.setPlaceholderText("Observações internas deste anúncio")
        form.addWidget(self.notes)
        body.addLayout(form, 3)

        side = QVBoxLayout()
        side.setSpacing(8)
        side.addWidget(label("Imagens do anúncio", object_name="sectionTitle"))
        side.addWidget(label("Marque e ordene as imagens; nenhuma marcada = todas do produto.", role="hint",
                             wrap=True))
        self.images = QListWidget()
        self.images.setIconSize(QSize(44, 44))
        self.images.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        chosen = listing.image_files
        order = chosen + [i.filename for i in self.product.images if i.filename not in chosen]
        by_name = {i.filename: i for i in self.product.images}
        for filename in order:
            image = by_name.get(filename)
            if image is None:
                continue
            item = QListWidgetItem(image.original_name or ("Principal" if image.is_main else filename[:12]))
            item.setData(Qt.ItemDataRole.UserRole, filename)
            item.setIcon(_thumb_icon(thumbnail(ctx.images.path_for(filename), 44)))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if filename in chosen else Qt.CheckState.Unchecked)
            self.images.addItem(item)
        self.images.setMaximumHeight(220)
        side.addWidget(self.images)
        quality_row = QHBoxLayout()
        quality_row.addWidget(label("Checagem", object_name="sectionTitle"), 1)
        self.quality_chip = StatusChip(text="", tone="neutral")
        self.quality_chip.setToolTip("Completude calculada pelo MLA a partir dos dados do catálogo (sem IA).")
        quality_row.addWidget(self.quality_chip)
        side.addLayout(quality_row)
        self.issue_box = QVBoxLayout()
        self.issue_box.setSpacing(6)
        side.addLayout(self.issue_box)
        if listing.marketplace is Marketplace.MERCADO_LIVRE and getattr(ctx, "mercadolivre", None) is not None:
            from mla.ui.pages.ml_tools import MLListingTools
            self.ml_tools = MLListingTools(self)
            side.addWidget(self.ml_tools)
        side.addStretch(1)
        holder = QWidget()
        holder.setLayout(side)
        holder.setFixedWidth(330)
        body.addWidget(holder)
        outer.addLayout(body, 1)

        foot = QHBoxLayout()
        self.foot_hint = label("", role="hint", wrap=True)
        foot.addWidget(self.foot_hint, 1)
        foot.addWidget(button("Cancelar", "ghost", None, self.reject))
        self.save_btn = button("Salvar", "secondary", "check", lambda: self._save(approve=False))
        self.approve_btn = button("Salvar e aprovar", "primary", "check-check", lambda: self._save(approve=True))
        foot.addWidget(self.save_btn)
        foot.addWidget(self.approve_btn)
        outer.addLayout(foot)
        for widget in (self.title_edit, self.price, self.stock, self.category_id, self.listing_type):
            widget.textChanged.connect(self._schedule)
            widget.setEnabled(self.editable)
        self.description.textChanged.connect(self._schedule)
        self.description.setReadOnly(not self.editable)
        self.images.itemChanged.connect(self._schedule)
        self.images.model().rowsMoved.connect(self._schedule)
        self.attributes.itemChanged.connect(self._schedule)
        self.save_btn.setEnabled(self.editable)
        self.approve_btn.setEnabled(self.editable)
        self._timer = QTimer(self, singleShot=True, interval=200, timeout=self._revalidate)
        self._loading = False
        self._revalidate()

    def _add_attribute(self, key: str = "", value: str = "") -> None:
        row = self.attributes.rowCount()
        self.attributes.insertRow(row)
        self.attributes.setItem(row, 0, QTableWidgetItem(key))
        self.attributes.setItem(row, 1, QTableWidgetItem(value))

    def _schedule(self, *_args) -> None:
        if not self._loading:
            self._timer.start()

    def collect(self) -> tuple[Listing, str]:
        """Listing with the edited overrides; second value is a format problem ("" = none)."""
        listing = replace(self.listing)
        listing.title = self.title_edit.text().strip()
        listing.description = self.description.toPlainText().strip()
        problem = ""
        try:
            listing.price_cents = parse_money_strict(self.price.text())
        except ParseError:
            problem = "Preço em formato inválido (use, por exemplo, 129,90)."
        stock = self.stock.text().strip()
        if stock and not stock.isdigit():
            problem = problem or "Estoque precisa ser um número inteiro."
        listing.stock = int(stock) if stock.isdigit() else None
        listing.category_id = self.category_id.text().strip()
        listing.listing_type = self.listing_type.text().strip()
        attributes = {}
        for row in range(self.attributes.rowCount()):
            key = (self.attributes.item(row, 0).text() if self.attributes.item(row, 0) else "").strip()
            value = (self.attributes.item(row, 1).text() if self.attributes.item(row, 1) else "").strip()
            if key and value:
                attributes[key] = value
        listing.attributes = attributes
        listing.image_files = [self.images.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.images.count())
                               if self.images.item(i).checkState() == Qt.CheckState.Checked]
        listing.notes = self.notes.text().strip()
        return listing, problem

    def _revalidate(self) -> None:
        listing, problem = self.collect()
        report = self.ctx.listings.validate(listing, self.product)
        rules = MARKETPLACE_RULES.get(listing.marketplace)
        title = listing.title or self.master.title
        if rules and rules.max_title:
            self.title_counter.setText(f"{len(title)}/{rules.max_title} caracteres"
                                       + ("" if rules.confirmed else " (limite ainda não confirmado no formulário real)"))
        else:
            self.title_counter.setText(f"{len(title)} caracteres")
        clear_layout(self.issue_box)
        issues = [("error", problem)] if problem else []
        issues += [(i.severity, i.message) for i in report.issues]
        errors = [m for s, m in issues if s == "error"]
        quality = self.ctx.quality.evaluate(listing)
        self.quality_chip.set_status(text=f"Completude {quality.score}%",
                                     tone="success" if quality.score >= 80 else "warning" if quality.score >= 50
                                     else "danger")
        issues += [("tip", text) for text in quality.improvements]
        if not issues:
            issues = [("ok", "Nenhuma pendência: pronto para aprovar.")]
        for severity, message in issues[:12]:
            self.issue_box.addWidget(_issue(severity, message))
        if len(issues) > 12:
            self.issue_box.addWidget(label(f"+{len(issues) - 12} item(ns)", role="hint"))
        self.approve_btn.setEnabled(self.editable and not errors)
        self.foot_hint.setText("Corrija as pendências em vermelho para aprovar." if errors else
                               "Aprovar não publica: o anúncio aprovado ainda passa pela fila e pela sua revisão final.")

    def _save(self, approve: bool) -> None:
        listing, problem = self.collect()
        if problem:
            inform(self, "Confira os campos", problem, error=True)
            return
        try:
            self.ctx.listings.save(listing)
            if approve:
                result = self.ctx.listings.approve([listing.id])
                if result.refused:
                    inform(self, "Não aprovado", result.refused[0][1], error=True)
                    return
        except ListingError as exc:
            inform(self, "Não foi possível salvar", str(exc), error=True)
            return
        self.accept()


def _thumb_icon(pm) -> QIcon:
    return QIcon(pm) if pm is not None and not pm.isNull() else icon("package", T.text_3, 44)


def _issue(severity: str, text: str) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    name, color = {"error": ("circle-x", T.danger), "warning": ("triangle-alert", T.warning),
                   "ok": ("circle-check", T.success), "tip": ("info", T.text_3)}.get(severity, ("info", T.text_2))
    glyph = label()
    glyph.setPixmap(pixmap(name, color, 16))
    glyph.setFixedWidth(18)
    layout.addWidget(glyph, 0, Qt.AlignmentFlag.AlignTop)
    layout.addWidget(label(text, wrap=True), 1)
    return row


# ---------------------------------------------------------------------------- table
class ListingModel(QAbstractTableModel):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.rows: list[ListingRow] = []
        self.total = 0
        self._loader = None
        self._pending: dict[int, str] = {}

    def load(self, loader, total: int) -> None:
        self.beginResetModel()
        self._loader, self.total = loader, total
        self.rows = loader(0, PAGE_SIZE) if total else []
        self._pending.clear()
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
            return COLUMNS[section]
        return None

    def pending(self, row: ListingRow) -> str:
        """First blocking problem, computed only for rows that are painted (validation loads the product)."""
        lid = row.listing.id
        if lid not in self._pending:
            status = row.listing.status
            if status.in_preparation or status in (ListingStatus.FAILED, ListingStatus.CANCELLED,
                                                   ListingStatus.NEEDS_ATTENTION):
                try:
                    report = self.ctx.listings.validate(row.listing)
                    errors = [i.message for i in report.issues if i.severity == "error"]
                    warnings = [i.message for i in report.issues if i.severity == "warning"]
                    text = errors[0] + (f" (+{len(errors) - 1})" if len(errors) > 1 else "") if errors else \
                        (f"{plural(len(warnings), 'aviso', 'avisos')}" if warnings else "")
                except ListingError as exc:
                    text = str(exc)
            elif status is ListingStatus.PUBLISHED:
                text = row.listing.external_id or "Publicação confirmada"
            else:
                text = ""
            self._pending[lid] = text
        return self._pending[lid]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.UserRole:
            return row
        if role == Qt.ItemDataRole.DisplayRole:
            return {0: row.product_name, 1: row.account_label, 2: row.title or "—",
                    3: format_money(row.price_cents) or "—", 4: row.listing.status.label,
                    5: self.pending(row)}.get(col)
        if role == Qt.ItemDataRole.ToolTipRole and col in (2, 5):
            return self.data(index)
        if role == Qt.ItemDataRole.ForegroundRole and col in (1, 3):
            return QColor(T.text_2)
        if role == Qt.ItemDataRole.ForegroundRole and col == 5:
            text = self.pending(row)
            return QColor(T.text_3 if not text or "aviso" in text else T.warning)
        if role == Qt.ItemDataRole.TextAlignmentRole and col == 3:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None


class ListingDelegate(QStyledItemDelegate):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx

    def paint(self, painter: QPainter, option, index) -> None:
        row: ListingRow = index.data(Qt.ItemDataRole.UserRole)
        col = index.column()
        if col not in (0, 4):
            super().paint(painter, option, index)
            return
        self.initStyleOption(option, index)
        option.text = ""
        option.widget.style().drawControl(option.widget.style().ControlElement.CE_ItemViewItem, option, painter,
                                          option.widget)
        rect = option.rect.adjusted(10, 0, -8, 0)
        if col == 4:
            fg, bg = tone_for(row.listing.status)
            paint_chip(painter, rect, row.listing.status.label, fg, bg, option.font)
            return
        painter.save()
        thumb = QRect(rect.left(), rect.center().y() - 20, 40, 40)
        pm = thumbnail(self.ctx.images.path_for(row.main_image), 40) if row.main_image else None
        if pm is not None and not pm.isNull():
            painter.drawPixmap(thumb, pm)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(T.raised))
            painter.drawRoundedRect(thumb, 6, 6)
            icon("package", T.text_3, 18).paint(painter, thumb.adjusted(11, 11, -11, -11))
        text = rect.adjusted(52, 9, 0, -9)
        bold = QFont(option.font)
        bold.setWeight(QFont.Weight.DemiBold)
        painter.setFont(bold)
        painter.setPen(QColor(T.text))
        painter.drawText(text, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                         painter.fontMetrics().elidedText(row.product_name, Qt.TextElideMode.ElideRight, text.width()))
        small = QFont(option.font)
        small.setPixelSize(12)
        painter.setFont(small)
        painter.setPen(QColor(T.text_3))
        painter.drawText(text, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft, row.sku)
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        return QSize(super().sizeHint(option, index).width(), ROW_HEIGHT)


# ---------------------------------------------------------------------------- page
class ListingsPage(Page):
    key = "listings"
    title = "Preparação de anúncios"

    def __init__(self, ctx, navigate, services=None, parent=None):
        super().__init__(ctx, navigate, parent)
        self.services = services
        self.send_btn = button("Enviar aprovados para a fila", "primary", "send", self._send)
        self.header.add_action(button("Exportar planilha", "secondary", "download", self._export))
        self.header.add_action(button("Preparar do catálogo", "secondary", "tag",
                                      lambda: self.navigate("products")))
        self.header.add_action(self.send_btn)
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.marketplace = QComboBox()
        for m in MARKETPLACES:
            self.marketplace.addItem(m.label, m)
        self.marketplace.currentIndexChanged.connect(self._marketplace_changed)
        bar.addWidget(self.marketplace)
        self.account = QComboBox()
        # account labels like "Loja Demo ML (filial)" must stay readable; the popup grows with them
        self.account.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.account.setMinimumWidth(200)
        self.account.view().setTextElideMode(Qt.TextElideMode.ElideNone)
        self.account.currentIndexChanged.connect(self.refresh)
        bar.addWidget(self.account)
        self.status_filter = QComboBox()
        for text, _ in FILTERS:
            self.status_filter.addItem(text)
        self.status_filter.currentIndexChanged.connect(self.refresh)
        bar.addWidget(self.status_filter)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar produto, SKU ou título")
        self.search.setClearButtonEnabled(True)
        self._debounce = QTimer(self, singleShot=True, interval=220, timeout=self.refresh)
        self.search.textChanged.connect(lambda _t: self._debounce.start())
        bar.addWidget(self.search, 1)
        self.root.addLayout(bar)
        self.summary = QHBoxLayout()
        self.summary.setSpacing(8)
        self.root.addLayout(self.summary)
        self.integration_note = Callout()
        self.root.addWidget(self.integration_note)

        actions = QHBoxLayout()
        self.count_label = label("", role="hint")
        actions.addWidget(self.count_label, 1)
        self.edit_btn = button("Editar", "ghost", "pencil", self._edit_selected)
        self.approve_btn = button("Aprovar", "secondary", "check-check", self._approve)
        self.revoke_btn = button("Revogar aprovação", "ghost", "rotate-ccw", self._revoke)
        self.product_btn = button("Abrir produto", "ghost", "package", self._open_product)
        self.delete_btn = button("Excluir", "danger", "trash-2", self._delete)
        for b in (self.edit_btn, self.approve_btn, self.revoke_btn, self.product_btn, self.delete_btn):
            actions.addWidget(b)
        self.root.addLayout(actions)

        self.model = ListingModel(ctx, self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setItemDelegate(ListingDelegate(ctx, self.table))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setHighlightSections(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        for col, width in ((1, 130), (2, 240), (3, 100), (4, 170)):
            header.resizeSection(col, width)
        self.table.doubleClicked.connect(lambda _i: self._edit_selected())
        self.table.selectionModel().selectionChanged.connect(self._sync)
        self.empty = EmptyState("tag", "Nenhum anúncio preparado",
                                "No Catálogo, selecione produtos e use Preparar anúncios para escolher o marketplace "
                                "e a conta de destino.",
                                button("Ir para o catálogo", "primary", "package", lambda: self.navigate("products")))
        holder = QWidget()
        self.stack = QStackedLayout(holder)
        self.stack.addWidget(self.table)
        self.stack.addWidget(self.empty)
        self.root.addWidget(holder, 1)
        self._marketplace_changed()

    # ------------------------------------------------------------------ data
    def _marketplace_changed(self) -> None:
        _account_combo(self.ctx, Marketplace(self.marketplace.currentData()), self.account, with_all=True,
                       active_only=False)
        self.refresh()

    def open_with(self, marketplace: Marketplace | None = None, account_id: int | None = None, **_) -> None:
        if marketplace is not None:
            self.marketplace.setCurrentIndex(self.marketplace.findData(marketplace))
        if account_id is not None:
            index = self.account.findData(account_id)
            if index >= 0:
                self.account.setCurrentIndex(index)
        self.status_filter.setCurrentIndex(0)
        self.refresh()

    def refresh(self) -> None:
        marketplace = Marketplace(self.marketplace.currentData())
        account_id = self.account.currentData()
        statuses = FILTERS[self.status_filter.currentIndex()][1]
        text = self.search.text()
        total = self.ctx.listings.count(marketplace, account_id, statuses, text)
        self.model.load(lambda offset, limit: self.ctx.listings.rows(marketplace, account_id, statuses, text, limit,
                                                                     offset), total)
        counts = self.ctx.listings.counts(marketplace, account_id)
        clear_layout(self.summary)
        groups = [("Precisam de correção", counts[ListingStatus.DRAFT] + counts[ListingStatus.INCOMPLETE], "warning"),
                  ("Prontos para revisão", counts[ListingStatus.READY], "violet"),
                  ("Aprovados", counts[ListingStatus.APPROVED], "active"),
                  ("Na fila ou em execução", counts[ListingStatus.QUEUED] + counts[ListingStatus.RUNNING]
                   + counts[ListingStatus.AWAITING_REVIEW], "neutral"),
                  ("Publicados confirmados", counts[ListingStatus.PUBLISHED], "success"),
                  ("Falha ou intervenção", counts[ListingStatus.FAILED] + counts[ListingStatus.NEEDS_ATTENTION],
                   "danger")]
        for text_, n, tone in groups:
            if n:
                self.summary.addWidget(StatusChip(text=f"{text_}: {n}", tone=tone))
        self.summary.addStretch(1)
        implemented = adapter_for(marketplace).implemented
        self.integration_note.set_text(
            "" if implemented else f"A publicação automática no {marketplace.label} ainda não está disponível. Você "
                                   "já pode preparar, revisar e aprovar os anúncios; o envio para a fila fica "
                                   "bloqueado até a integração ser validada no formulário real.")
        self.send_btn.setEnabled(implemented and counts[ListingStatus.APPROVED] > 0 and self.services is not None)
        self.header.set_subtitle(f"{plural(sum(counts.values()), 'anúncio', 'anúncios')} no {marketplace.label}"
                                 + (" nesta conta" if account_id else ""))
        self.stack.setCurrentIndex(0 if total or self.search.text() or statuses else 1)
        self._sync()

    def _selected(self) -> list[ListingRow]:
        model = self.table.selectionModel()
        if model is None:
            return []
        return [self.model.rows[i.row()] for i in model.selectedRows() if i.row() < len(self.model.rows)]

    def _sync(self, *_args) -> None:
        rows = self._selected()
        n = len(rows)
        self.edit_btn.setVisible(n == 1)
        self.product_btn.setVisible(n == 1)
        self.approve_btn.setVisible(any(r.listing.status in (ListingStatus.READY, ListingStatus.INCOMPLETE,
                                                              ListingStatus.DRAFT) for r in rows))
        self.revoke_btn.setVisible(any(r.listing.status is ListingStatus.APPROVED for r in rows))
        self.delete_btn.setVisible(n > 0)
        if n:
            self.count_label.setText(plural(n, "selecionado", "selecionados"))
        else:
            self.count_label.setText(f"{plural(self.model.total, 'anúncio exibido', 'anúncios exibidos')}. Clique "
                                     "duas vezes para revisar o conteúdo." if self.model.total else "")

    # ------------------------------------------------------------------ actions
    def _edit_selected(self) -> None:
        rows = self._selected()
        if len(rows) != 1:
            return
        listing = self.ctx.listings.get(rows[0].listing.id)
        if listing is None:
            return
        editor = ListingEditor(self.ctx, listing, self)
        if editor.exec():
            show_toast(self, "Anúncio salvo", "success")
        self.refresh()

    def _approve(self) -> None:
        rows = self._selected()
        result = self.ctx.listings.approve([r.listing.id for r in rows])
        self.refresh()
        if result.refused:
            details = "\n".join(f"{next((r.product_name for r in rows if r.listing.id == lid), lid)}: {reason}"
                                for lid, reason in result.refused[:12])
            inform(self, "Alguns anúncios não foram aprovados",
                   f"{len(result.approved)} aprovado(s). Pendências:\n\n{details}")
        else:
            show_toast(self, f"{len(result.approved)} anúncio(s) aprovado(s)", "success")

    def _revoke(self) -> None:
        count = self.ctx.listings.revoke([r.listing.id for r in self._selected()])
        self.refresh()
        show_toast(self, f"Aprovação revogada em {count} anúncio(s)")

    def _delete(self) -> None:
        rows = self._selected()
        if not rows or not confirm(self, "Excluir anúncios", f"Excluir {plural(len(rows), 'anúncio preparado', 'anúncios preparados')}? "
                                   "O produto mestre não é alterado.", "Excluir", danger=True):
            return
        try:
            count = self.ctx.listings.delete([r.listing.id for r in rows])
        except ListingError as exc:
            inform(self, "Não foi possível excluir", str(exc), error=True)
            return
        self.refresh()
        show_toast(self, f"{count} anúncio(s) excluído(s)")

    def _open_product(self) -> None:
        rows = self._selected()
        if len(rows) == 1:
            self.navigate("products", product_id=rows[0].listing.product_id)

    def _export(self) -> None:
        """Intermediate spreadsheet of the listings in the current filter (one row per variation + photos)."""
        marketplace = Marketplace(self.marketplace.currentData())
        account_id = self.account.currentData()
        statuses = FILTERS[self.status_filter.currentIndex()][1]
        rows = self.ctx.listings.rows(marketplace, account_id, statuses, self.search.text(), limit=10_000)
        if not rows:
            inform(self, "Exportar planilha", "Nenhum anúncio no filtro atual.")
            return
        default = self.ctx.paths.exports / f"anuncios-{marketplace.value}-{datetime.now():%Y-%m-%d}.xlsx"
        path, _ = QFileDialog.getSaveFileName(self, "Exportar anúncios", str(default),
                                              "Planilha Excel (*.xlsx);;Planilha CSV (*.csv)")
        if not path:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = ListingExporter(self.ctx).export_listings([r.listing for r in rows], Path(path))
        except (OSError, ValueError) as exc:
            QApplication.restoreOverrideCursor()
            inform(self, "Não foi possível exportar", str(exc), error=True)
            return
        QApplication.restoreOverrideCursor()
        where = f"\nFotos: {result.photos_dir}" if result.photos_dir else ""
        inform(self, "Planilha exportada", f"{result.summary()}\n\nArquivo: {path}{where}\n\n{NOTICE}")

    def _send(self) -> None:
        marketplace = Marketplace(self.marketplace.currentData())
        account_id = self.account.currentData()
        approved = [r.listing for r in self.ctx.listings.rows(marketplace, account_id, [ListingStatus.APPROVED],
                                                             limit=10_000)]
        if not approved:
            return
        if not confirm(self, "Enviar para a fila", f"Enviar {plural(len(approved), 'anúncio aprovado', 'anúncios aprovados')} "
                       "para a fila de automação? Cada um ainda para na revisão final antes de publicar.",
                       "Enviar para a fila"):
            return
        result = self.services.queue.enqueue_listings(approved, self.ctx.listings.block_reason)
        self.refresh()
        if result.skipped:
            details = "\n".join(f"{s.product_name}: {s.reason}" for s in result.skipped[:12])
            inform(self, "Fila atualizada", f"{result.summary()}.\n\n{details}")
        else:
            show_toast(self, f"{result.summary()}. Acompanhe em Automações.", "success")


__all__ = ["ListingEditor", "ListingsPage", "PrepareListingsDialog"]
