from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QLineEdit, QListWidget,
    QStackedLayout, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from mla.core.enums import ItemStatus, Marketplace
from mla.core.models import JobItem
from mla.ui.icons import icon
from mla.ui.pages.base import Page
from mla.ui.theme import T
from mla.ui.widgets.common import (
    EmptyState, StatusChip, StatusDelegate, button, divider, format_when, label, show_toast,
)

HEADERS = ["Produto", "SKU", "Marketplace", "Conta", "Status", "Etapa", "Início", "Resultado"]
STEP_LABELS = {
    "validate": "Validação", "duplicates": "Duplicidade", "open_browser": "Abrir navegador",
    "login": "Autenticação", "open_form": "Abrir formulário", "category": "Categoria",
    "attributes": "Atributos", "title": "Título", "images": "Imagens", "description": "Descrição",
    "price": "Preço", "stock": "Estoque", "logistics": "Logística", "review": "Conferência",
    "await_approval": "Aguardando aprovação", "publish": "Publicação", "confirm": "Confirmação",
    "done": "Concluído",
}


def duration(item: JobItem) -> str:
    if not item.started_at or not item.finished_at:
        return ""
    seconds = int((datetime.fromisoformat(item.finished_at) - datetime.fromisoformat(item.started_at)).total_seconds())
    return f"{seconds // 60}min {seconds % 60:02d}s" if seconds >= 60 else f"{seconds}s"


def result_text(item: JobItem) -> str:
    if item.status is ItemStatus.PUBLISHED:
        return item.url or item.external_id or "Publicado"
    return item.error


class ItemDetails(QDialog):
    def __init__(self, ctx, item: JobItem, parent=None):
        super().__init__(parent)
        self.ctx, self.item = ctx, item
        self.setWindowTitle("Detalhes da execução")
        self.resize(720, 620)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(10)
        head = QHBoxLayout()
        head.addWidget(label(item.product_name or "(produto excluído)", object_name="sectionTitle"), 1)
        head.addWidget(StatusChip(item.status))
        layout.addLayout(head)
        meta = [("SKU", item.sku), ("Marketplace", item.marketplace.label), ("Conta", item.account_label),
                ("Etapa", STEP_LABELS.get(item.step, item.step)), ("Início", (item.started_at or "").replace("T", " ")),
                ("Fim", (item.finished_at or "").replace("T", " ")), ("Duração", duration(item)),
                ("Tentativas", str(item.attempts)), ("ID externo", item.external_id)]
        for key, value in meta:
            if value:
                row = QHBoxLayout()
                k = label(key, role="muted")
                k.setFixedWidth(110)
                row.addWidget(k)
                row.addWidget(label(value), 1)
                layout.addLayout(row)
        if item.url:
            layout.addWidget(button("Abrir anúncio", "secondary", "external-link",
                                    lambda: QDesktopServices.openUrl(QUrl(item.url))), 0, Qt.AlignmentFlag.AlignLeft)
        if item.error:
            err = label(item.error, wrap=True)
            err.setStyleSheet(f"color: {T.danger};")
            err.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(err)
        layout.addWidget(divider())
        layout.addWidget(label("Registro da execução", role="muted"))
        logs = QListWidget()
        self.screenshots: list[str] = []
        for entry in ctx.automation_repo.logs_for_item(item.id):
            text = f"{entry.created_at[11:19]}  {STEP_LABELS.get(entry.step, entry.step):<18}  {entry.message}"
            row = logs.count()
            logs.addItem(text)
            color = {"ERROR": T.danger, "WARNING": T.warning}.get(entry.level)
            if color:
                logs.item(row).setForeground(QColor(color))
            if entry.screenshot:
                self.screenshots.append(entry.screenshot)
        layout.addWidget(logs, 1)
        foot = QHBoxLayout()
        if self.screenshots:
            foot.addWidget(button("Abrir captura de tela", "ghost", "eye", self._open_screenshot))
        foot.addStretch(1)
        self.rerun = False
        if item.status in (ItemStatus.FAILED, ItemStatus.CANCELLED, ItemStatus.NEEDS_ATTENTION, ItemStatus.SKIPPED):
            foot.addWidget(button("Reexecutar", "secondary", "rotate-ccw", self._rerun))
        foot.addWidget(button("Fechar", "primary", None, self.accept))
        layout.addLayout(foot)

    def _open_screenshot(self) -> None:
        path = self.ctx.paths.artifacts / self.screenshots[-1]
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _rerun(self) -> None:
        self.rerun = True
        self.accept()


class HistoryPage(Page):
    key = "history"
    title = "Histórico"
    subtitle = "Cada combinação de produto, marketplace e conta executada."

    def __init__(self, ctx, navigate, parent=None):
        super().__init__(ctx, navigate, parent)
        self.header.add_action(button("Exportar CSV", "secondary", "download", self._export))
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar por produto, SKU, erro ou ID do anúncio")
        self.search.addAction(icon("search", T.text_3, 16), QLineEdit.ActionPosition.LeadingPosition)
        self.search.setClearButtonEnabled(True)
        self._debounce = QTimer(self, singleShot=True, interval=220, timeout=self.refresh)
        self.search.textChanged.connect(lambda _t: self._debounce.start())
        bar.addWidget(self.search, 1)
        self.market = QComboBox()
        self.market.addItem("Todos os marketplaces", None)
        for marketplace in Marketplace:
            self.market.addItem(marketplace.label, marketplace)
        self.market.currentIndexChanged.connect(self.refresh)
        bar.addWidget(self.market)
        self.status = QComboBox()
        self.status.addItem("Todos os status", None)
        for status in ItemStatus:
            if status is not ItemStatus.QUEUED:
                self.status.addItem(status.label, status)
        self.status.currentIndexChanged.connect(self.refresh)
        bar.addWidget(self.status)
        self.root.addLayout(bar)

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(44)
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setItemDelegateForColumn(4, StatusDelegate(self.table, ItemStatus))
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        for col, width in ((1, 104), (2, 146), (3, 112), (4, 156), (5, 104), (6, 96)):
            header.resizeSection(col, width)
        self.table.doubleClicked.connect(self._details)
        holder = QWidget()
        self.stack = QStackedLayout(holder)
        self.stack.addWidget(self.table)
        self.stack.addWidget(EmptyState("history", "Sem execuções registradas",
                                        "Quando você executar produtos ou grupos, cada tentativa aparece aqui com "
                                        "status, duração e o link do anúncio publicado."))
        self.root.addWidget(holder, 1)
        self._items: list[JobItem] = []

    def open_with(self, status: ItemStatus | None = None, **_):
        if status is not None:
            self.status.setCurrentIndex(self.status.findData(status))

    def refresh(self) -> None:
        self._items = self.ctx.automation_repo.history(self.search.text().strip(), self.market.currentData(),
                                                       self.status.currentData())
        self.table.setRowCount(len(self._items))
        for row, item in enumerate(self._items):
            values = [item.product_name or "(excluído)", item.sku, item.marketplace.label, item.account_label,
                      "", STEP_LABELS.get(item.step, item.step), format_when(item.started_at), result_text(item)]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if col == 4:
                    cell.setData(Qt.ItemDataRole.UserRole, item.status)
                if col in (1, 3, 5, 6):
                    cell.setForeground(QColor(T.text_2))
                if col == 6 and duration(item):
                    cell.setToolTip(f"Duração: {duration(item)}")
                if col == 7:
                    cell.setToolTip(value)
                    if item.status in (ItemStatus.FAILED, ItemStatus.NEEDS_ATTENTION):
                        cell.setForeground(QColor(T.danger))
                self.table.setItem(row, col, cell)
        empty = not self._items and not (self.search.text() or self.market.currentData() or self.status.currentData())
        self.stack.setCurrentIndex(1 if empty else 0)

    def _details(self, index) -> None:
        item = self._items[index.row()]
        dialog = ItemDetails(self.ctx, item, self)
        dialog.exec()
        if dialog.rerun and item.product_id:
            self.navigate("automations", rerun_item=item.id)

    def _export(self) -> None:
        default = str(self.ctx.paths.exports / f"historico-{datetime.now():%Y%m%d-%H%M}.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Exportar histórico", default, "Planilha CSV (*.csv)")
        if not path:
            return
        with Path(path).open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.writer(fh, delimiter=";")
            writer.writerow(["produto", "sku", "marketplace", "conta", "status", "etapa", "inicio", "fim",
                             "duracao", "tentativas", "id_externo", "url", "erro"])
            for item in self._items:
                writer.writerow([item.product_name, item.sku, item.marketplace.label, item.account_label,
                                 item.status.label, STEP_LABELS.get(item.step, item.step), item.started_at or "",
                                 item.finished_at or "", duration(item), item.attempts, item.external_id, item.url,
                                 item.error])
        show_toast(self, f"{len(self._items)} registro(s) exportado(s)", "success")
