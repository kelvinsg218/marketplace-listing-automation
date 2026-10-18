"""Central de Importações: history of imports and the import wizard.

Wizard steps (the 11 stages of the brief, grouped): Arquivo (choose, detect format) → Prévia (read and
preview) → Mapeamento (recognised columns, user corrections, options) → Revisão (validation, duplicates,
images, changes, decisions, confirmation) → Concluído (report). Planning and commit run on a worker thread.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QHeaderView, QInputDialog,
    QLineEdit, QListWidget, QMenu, QPlainTextEdit, QProgressBar, QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from mla.core.enums import DataSource, ImportAction, ImportStatus
from mla.importing.mapping import IGNORE, fields_for, mapping_problems
from mla.importing.readers import FORMAT_LABELS
from mla.importing.service import Analysis, ImportCancelled, ImportOptions, ImportProblem
from mla.ui.pages.base import Page
from mla.ui.theme import T
from mla.ui.widgets.common import (
    Callout, EmptyState, Panel, StatusChip, StatusDelegate, StepRail, button, confirm, format_when, inform, label,
    plural, show_toast,
)
from mla.ui.workers import TaskRunner

TARGETS = [("products", "Produtos (catálogo mestre)"), ("compatibility", "Compatibilidades")]
TARGET_LABELS = {"products": "Produtos", "compatibility": "Compatibilidades", "images": "Imagens"}
FILE_FILTER = ("Bases de produtos (*.csv *.txt *.tsv *.xlsx *.xlsm *.json *.xml *.pdf *.zip);;"
               "Todos os arquivos (*.*)")
PAGE_SIZE = 200
DECISION_LABELS = {"create": "Criar", "update": "Atualizar", "skip": "Ignorar"}
FILTERS = [("Todas as linhas", None, False), ("Novos", [ImportAction.CREATE], False),
           ("Atualizações", [ImportAction.UPDATE], False), ("Para revisar", [ImportAction.REVIEW], False),
           ("Com erro", [ImportAction.ERROR], False), ("Sem mudanças", [ImportAction.UNCHANGED, ImportAction.SKIP],
                                                       False), ("Com avisos", None, True)]


def _table(columns: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(columns))
    table.setHorizontalHeaderLabels(columns)
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setWordWrap(False)
    table.setShowGrid(False)
    table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    table.horizontalHeader().setHighlightSections(False)
    table.verticalHeader().setDefaultSectionSize(34)
    return table


def _item(text: str, data=None, muted: bool = False) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    if data is not None:
        item.setData(Qt.ItemDataRole.UserRole, data)
    if muted:
        item.setForeground(QColor(T.text_3))
    item.setToolTip(text if len(text) > 40 else "")
    return item


# ---------------------------------------------------------------------------- wizard
class ImportWizard(QDialog):
    STEPS = ["Arquivo", "Prévia", "Mapeamento", "Revisão", "Concluído"]

    def __init__(self, ctx, parent=None, batch_id: int | None = None, path: Path | None = None,
                 target: str = "products"):
        super().__init__(parent)
        self.ctx = ctx
        self.service = ctx.imports
        self.analysis: Analysis | None = None
        self.batch_id = batch_id
        self.changed_catalog = False
        self._page = 0
        self._combos: dict[str, QComboBox] = {}
        self.setWindowTitle("Central de Importações")
        self.resize(1160, 780)
        self.setMinimumSize(980, 660)
        self.runner = TaskRunner(self, cancelled_types=(ImportCancelled,))
        self.runner.progress.connect(self._on_progress)
        self.runner.finished.connect(self._task_done)
        self.runner.failed.connect(self._task_failed)
        self.runner.cancelled.connect(self._task_cancelled)
        self._task = "plan"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 18)
        outer.setSpacing(14)
        head = QHBoxLayout()
        head.addWidget(label("Nova importação", object_name="pageTitle"), 1)
        outer.addLayout(head)
        self.rail = StepRail(self.STEPS)
        outer.addWidget(self.rail)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)
        self.stack.addWidget(self._build_file())
        self.stack.addWidget(self._build_preview())
        self.stack.addWidget(self._build_mapping())
        self.stack.addWidget(self._build_review())
        self.stack.addWidget(self._build_done())

        self.progress_row = QWidget()
        prog = QHBoxLayout(self.progress_row)
        prog.setContentsMargins(0, 0, 0, 0)
        self.progress_text = label("", role="muted")
        prog.addWidget(self.progress_text, 1)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(260)
        prog.addWidget(self.progress_bar)
        self.cancel_task_btn = button("Cancelar operação", "ghost", "x", self._cancel_task)
        prog.addWidget(self.cancel_task_btn)
        self.progress_row.hide()
        outer.addWidget(self.progress_row)

        foot = QHBoxLayout()
        self.footer_hint = label("", role="hint", wrap=True)
        foot.addWidget(self.footer_hint, 1)
        self.back_btn = button("Voltar", "ghost", None, self._back)
        self.close_btn = button("Fechar", "ghost", None, self.reject)
        self.next_btn = button("Avançar", "primary", None, self._next)
        for b in (self.back_btn, self.close_btn, self.next_btn):
            foot.addWidget(b)
        outer.addLayout(foot)

        if path is not None:
            self.target.setCurrentIndex(max(0, self.target.findData(target)))
            QTimer.singleShot(0, lambda: self._analyze(Path(path)))
        if batch_id is not None:
            self._go(3)
            self._load_review()
        else:
            self._go(0)

    # ------------------------------------------------------------------ step 1: file
    def _build_file(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(14)
        row = QHBoxLayout()
        row.addWidget(label("O que você vai importar?", role="muted"))
        self.target = QComboBox()
        for key, text in TARGETS:
            self.target.addItem(text, key)
        self.target.currentIndexChanged.connect(self._on_target)
        row.addWidget(self.target)
        row.addStretch(1)
        layout.addLayout(row)
        picks = QHBoxLayout()
        picks.addWidget(button("Escolher arquivo…", "primary", "file-up", self._pick_file))
        self.folder_btn = button("Associar imagens de uma pasta…", "secondary", "folder-input", self._pick_folder,
                                 "Fotos com o SKU no nome (ABC-1.jpg, ABC-1_2.jpg) são ligadas aos produtos.")
        picks.addWidget(self.folder_btn)
        picks.addStretch(1)
        layout.addLayout(picks)
        layout.addWidget(label("Aceita CSV, planilha XLSX, JSON, XML, PDF com tabela ou ficha técnica e ZIP com "
                               "planilha e imagens. Nada é gravado no catálogo antes da sua confirmação.",
                               role="hint", wrap=True))
        self.file_panel = Panel("Arquivo selecionado")
        self.file_info = label("", wrap=True)
        self.file_panel.add(self.file_info)
        self.sheet_row = QWidget()
        sr = QHBoxLayout(self.sheet_row)
        sr.setContentsMargins(0, 0, 0, 0)
        sr.addWidget(label("Aba da planilha", role="muted"))
        self.sheet = QComboBox()
        self.sheet.activated.connect(self._on_sheet)
        sr.addWidget(self.sheet)
        sr.addStretch(1)
        self.file_panel.add(self.sheet_row)
        self.zip_choice = QWidget()
        zc = QVBoxLayout(self.zip_choice)
        zc.setContentsMargins(0, 0, 0, 0)
        zc.addWidget(label("O ZIP tem mais de um arquivo de catálogo. Escolha qual importar:", role="muted"))
        self.zip_list = QListWidget()
        self.zip_list.setMaximumHeight(140)
        self.zip_list.itemDoubleClicked.connect(lambda _i: self._choose_zip_table())
        zc.addWidget(self.zip_list)
        zc.addWidget(button("Usar o arquivo selecionado", "secondary", None, self._choose_zip_table))
        self.file_panel.add(self.zip_choice)
        self.skipped_note = Callout(warn=True)
        self.file_panel.add(self.skipped_note)
        self.file_panel.hide()
        layout.addWidget(self.file_panel)
        layout.addStretch(1)
        return page

    def _on_target(self) -> None:
        self.folder_btn.setVisible(self.target.currentData() == "products")
        if self.analysis is not None and self.analysis.info is not None:
            self.service.retarget(self.analysis, self.target.currentData())
            self._fill_mapping()

    def _pick_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Escolher base para importar", "", FILE_FILTER)
        if path:
            self._analyze(Path(path))

    def _pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Pasta com as fotos dos produtos")
        if folder:
            self._analyze(Path(folder))

    def _analyze(self, path: Path, sheet: str | None = None) -> None:
        self._discard_analysis()
        try:
            self.analysis = self.service.analyze(path, self.target.currentData(), sheet)
        except (ImportProblem, OSError) as exc:
            inform(self, "Não foi possível ler o arquivo", str(exc), error=True)
            return
        self._show_file()

    def _show_file(self) -> None:
        a = self.analysis
        self.file_panel.show()
        self.file_panel.title.setText(a.path.name)
        lines = [f"Formato identificado: {FORMAT_LABELS.get(a.format, 'Pasta de imagens')}"]
        if a.info:
            lines.append(f"Tabela lida: {a.table_path.name if a.table_path else ''}, "
                         f"{plural(len(a.headers), 'coluna', 'colunas')}"
                         + (f", cerca de {a.info.total_rows} linha(s)" if a.info.total_rows else ""))
            lines += a.info.notes
        if a.archive:
            lines.append(f"No ZIP: {plural(len(a.archive.images), 'imagem', 'imagens')}, "
                         f"{plural(len(a.archive.documents), 'documento', 'documentos')}.")
        if a.images_only:
            count = len(a.archive.images) if a.archive else 0
            lines.append("Somente imagens: serão ligadas aos produtos cujo SKU aparece no nome do arquivo"
                         + (f" ({count} imagens)." if count else "."))
        if a.template:
            lines.append(f"Modelo de importação reconhecido: {a.template.name}.")
        self.file_info.setText("\n".join(lines))
        sheets = a.info.sheets if a.info else []
        self.sheet_row.setVisible(len(sheets) > 1)
        self.sheet.clear()
        self.sheet.addItems(sheets)
        if a.info and a.info.sheet:
            self.sheet.setCurrentText(a.info.sheet)
        self.zip_choice.setVisible(a.needs_table_choice)
        self.zip_list.clear()
        for candidate in a.table_candidates:
            self.zip_list.addItem(a.archive.relative(candidate))
        skipped = a.archive.skipped if a.archive else []
        self.skipped_note.set_text(
            f"{plural(len(skipped), 'arquivo do ZIP foi ignorado', 'arquivos do ZIP foram ignorados')} por segurança "
            "ou por não serem usados (executáveis, scripts, macros, atalhos, outros compactados): "
            + ", ".join(name for name, _ in skipped[:6]) + ("…" if len(skipped) > 6 else "") if skipped else "")
        self._sync()

    def _on_sheet(self) -> None:
        if self.analysis and self.analysis.table_path:
            try:
                self.service.choose_table(self.analysis, self.analysis.table_path, self.sheet.currentText())
            except ImportProblem as exc:
                inform(self, "Aba sem dados", str(exc), error=True)
                return
            self._show_file()

    def _choose_zip_table(self) -> None:
        row = self.zip_list.currentRow()
        if self.analysis is None or row < 0:
            return
        try:
            self.service.choose_table(self.analysis, self.analysis.table_candidates[row])
        except ImportProblem as exc:
            inform(self, "Não foi possível ler o arquivo", str(exc), error=True)
            return
        self._show_file()

    # ------------------------------------------------------------------ step 2: preview
    def _build_preview(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        self.preview_note = Callout()
        layout.addWidget(self.preview_note)
        self.preview_table = _table([])
        layout.addWidget(self.preview_table, 1)
        return page

    def _fill_preview(self) -> None:
        a = self.analysis
        headers = a.headers
        self.preview_table.clear()
        self.preview_table.setColumnCount(len(headers) + 1)
        self.preview_table.setHorizontalHeaderLabels(["Onde", *headers])
        self.preview_table.setRowCount(len(a.preview))
        flagged = 0
        for r, row in enumerate(a.preview):
            where = _item(row.where + ("  (revisar)" if row.review else ""))
            if row.review:
                flagged += 1
                where.setToolTip(row.review)
                where.setForeground(QColor(T.warning))
            self.preview_table.setItem(r, 0, where)
            for c, header in enumerate(headers, start=1):
                self.preview_table.setItem(r, c, _item(str(row.values.get(header, ""))))
        self.preview_table.resizeColumnsToContents()
        for c in range(self.preview_table.columnCount()):
            if self.preview_table.columnWidth(c) > 260:
                self.preview_table.setColumnWidth(c, 260)
        text = f"Primeiras {len(a.preview)} linhas do arquivo, exatamente como foram lidas."
        if flagged:
            text += f" {plural(flagged, 'linha precisa', 'linhas precisam')} de revisão (passe o mouse em “Onde”)."
        self.preview_note.set_text(text)

    # ------------------------------------------------------------------ step 3: mapping
    def _build_mapping(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(10)
        self.mapping_note = Callout()
        layout.addWidget(self.mapping_note)
        self.mapping_table = _table(["Coluna do arquivo", "Exemplo", "Campo no MLA", "Reconhecimento"])
        header = self.mapping_table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.resizeSection(0, 200)
        header.resizeSection(2, 300)
        header.resizeSection(3, 260)
        self.mapping_table.verticalHeader().setDefaultSectionSize(40)
        layout.addWidget(self.mapping_table, 1)
        options = QHBoxLayout()
        options.setSpacing(16)
        self.update_existing = QCheckBox("Atualizar produtos já cadastrados (só os campos preenchidos no arquivo)")
        self.update_existing.setChecked(True)
        options.addWidget(self.update_existing)
        self.match_by_sku = QCheckBox("Ligar imagens com o SKU no nome")
        self.match_by_sku.setChecked(True)
        options.addWidget(self.match_by_sku)
        self.source_combo = QComboBox()
        for source in DataSource:
            if source is not DataSource.AI:
                self.source_combo.addItem(f"Origem: {source.label}", source.value)
        self.source_combo.setToolTip("Dados do cliente entram como confirmados; as outras origens entram como "
                                     "não verificadas.")
        options.addWidget(self.source_combo)
        options.addStretch(1)
        layout.addLayout(options)
        media = QHBoxLayout()
        media.addWidget(label("Pasta extra de imagens", role="muted"))
        self.media_folder = QLineEdit()
        self.media_folder.setPlaceholderText("Opcional: onde estão as fotos citadas na planilha")
        media.addWidget(self.media_folder, 1)
        media.addWidget(button("Procurar…", "ghost", "folder-open", self._pick_media_folder))
        media.addSpacing(16)
        media.addWidget(button("Salvar como modelo…", "ghost", "copy", self._save_template))
        layout.addLayout(media)
        self.confirm_probable = QCheckBox("Revisei os campos marcados como “confirme”")
        self.confirm_probable.toggled.connect(self._sync)
        layout.addWidget(self.confirm_probable)
        return page

    def _fill_mapping(self) -> None:
        a = self.analysis
        target = a.target
        sample = {h: next((r.values.get(h, "") for r in a.preview if r.values.get(h, "").strip()), "")
                  for h in a.headers}
        self.mapping_table.setRowCount(len(a.suggestions))
        self._combos.clear()
        groups: list[str] = []
        for r, suggestion in enumerate(a.suggestions):
            self.mapping_table.setItem(r, 0, _item(suggestion.column))
            self.mapping_table.setItem(r, 1, _item(sample.get(suggestion.column, ""), muted=True))
            combo = QComboBox()
            combo.addItem("Ignorar coluna", IGNORE)
            groups.clear()
            for spec in fields_for(target):
                if spec.group not in groups:
                    groups.append(spec.group)
                    combo.insertSeparator(combo.count())
                combo.addItem(f"{spec.label}", spec.key)
            combo.setCurrentIndex(max(0, combo.findData(suggestion.field)))
            combo.currentIndexChanged.connect(self._sync)
            self.mapping_table.setCellWidget(r, 2, combo)
            self._combos[suggestion.column] = combo
            text = {"exact": "Reconhecida", "probable": "Provável: confirme", "template": "Do modelo salvo",
                    "none": "Não reconhecida"}[suggestion.confidence]
            item = _item(text)
            item.setToolTip(suggestion.reason)
            if suggestion.confidence == "probable":
                item.setForeground(QColor(T.warning))
            elif suggestion.confidence == "none":
                item.setForeground(QColor(T.text_3))
            self.mapping_table.setItem(r, 3, item)
        is_products = target == "products" and not a.images_only
        self.update_existing.setVisible(is_products)
        self.match_by_sku.setVisible(is_products)
        self.source_combo.setVisible(target == "compatibility")
        probable = sum(1 for s in a.suggestions if s.confidence == "probable")
        self.confirm_probable.setVisible(bool(probable))
        self.confirm_probable.setChecked(False)
        recognized = sum(1 for s in a.suggestions if s.field)
        self.mapping_note.set_text(
            f"{recognized} de {len(a.suggestions)} colunas reconhecidas automaticamente pelo nome. Corrija o campo "
            "de cada coluna se precisar; colunas ignoradas não são importadas."
            + (f" {plural(probable, 'coluna está marcada', 'colunas estão marcadas')} como provável: confirme antes "
               "de analisar." if probable else ""))

    def mapping(self) -> dict[str, str]:
        return {column: combo.currentData() or "" for column, combo in self._combos.items()}

    def options(self) -> ImportOptions:
        return ImportOptions(update_existing=self.update_existing.isChecked(), media_folder=self.media_folder.text(),
                             match_images_by_sku=self.match_by_sku.isChecked(),
                             source=self.source_combo.currentData() or DataSource.CLIENT.value)

    def _pick_media_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Pasta com as imagens citadas")
        if folder:
            self.media_folder.setText(folder)

    def _save_template(self) -> None:
        name, ok = QInputDialog.getText(self, "Salvar modelo de importação",
                                        "Nome do modelo (ex.: ERP da loja, planilha do fornecedor X):")
        if not ok or not name.strip():
            return
        try:
            self.service.save_template(name, self.analysis, self.mapping(), self.options())
        except (ImportProblem, ValueError) as exc:
            inform(self, "Modelo não salvo", str(exc), error=True)
            return
        show_toast(self, f"Modelo “{name.strip()}” salvo; será sugerido em arquivos com as mesmas colunas.", "success")

    # ------------------------------------------------------------------ step 4: review
    def _build_review(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(10)
        self.summary_row = QHBoxLayout()
        self.summary_row.setSpacing(8)
        layout.addLayout(self.summary_row)
        self.review_note = Callout()
        layout.addWidget(self.review_note)
        bar = QHBoxLayout()
        self.filter = QComboBox()
        for text, _, _ in FILTERS:
            self.filter.addItem(text)
        self.filter.currentIndexChanged.connect(lambda _i: self._load_rows(0))
        bar.addWidget(self.filter)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar SKU ou nome")
        self.search.setClearButtonEnabled(True)
        self._search_timer = QTimer(self, singleShot=True, interval=250, timeout=lambda: self._load_rows(0))
        self.search.textChanged.connect(lambda _t: self._search_timer.start())
        bar.addWidget(self.search, 1)
        self.include_btn = button("Incluir selecionadas", "secondary", "check", lambda: self._decide("include"))
        self.skip_btn = button("Ignorar selecionadas", "ghost", "ban", lambda: self._decide("skip"))
        bar.addWidget(self.include_btn)
        bar.addWidget(self.skip_btn)
        more = button("Em massa", "ghost", "list-checks")
        menu = QMenu(self)
        menu.addAction("Atualizar todos os já cadastrados", lambda: self._bulk(ImportAction.UPDATE, "update"))
        menu.addAction("Ignorar todos os já cadastrados", lambda: self._bulk(ImportAction.UPDATE, "skip"))
        menu.addAction("Incluir todas as linhas para revisar", lambda: self._bulk(ImportAction.REVIEW, "include"))
        menu.addAction("Ignorar todos os novos", lambda: self._bulk(ImportAction.CREATE, "skip"))
        menu.addAction("Criar todos os novos", lambda: self._bulk(ImportAction.CREATE, "create"))
        more.setMenu(menu)
        bar.addWidget(more)
        bar.addWidget(button("Exportar relatório…", "ghost", "download", self._export_report))
        layout.addLayout(bar)
        split = QSplitter(Qt.Orientation.Vertical)
        self.rows_table = _table(["Linha", "SKU", "Nome", "Análise", "Decisão", "Resumo"])
        self.rows_table.setItemDelegateForColumn(3, StatusDelegate(self.rows_table, ImportAction))
        self.rows_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        h = self.rows_table.horizontalHeader()
        for col, width in ((0, 90), (1, 140), (2, 240), (3, 140), (4, 90)):
            h.resizeSection(col, width)
        h.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.rows_table.itemSelectionChanged.connect(self._show_detail)
        split.addWidget(self.rows_table)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setPlaceholderText("Selecione uma linha para ver as alterações, os avisos e as imagens.")
        split.addWidget(self.detail)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        layout.addWidget(split, 1)
        pager = QHBoxLayout()
        self.page_label = label("", role="hint")
        pager.addWidget(self.page_label, 1)
        self.prev_btn = button("Anteriores", "ghost", None, lambda: self._load_rows(self._offset - PAGE_SIZE))
        self.next_page_btn = button("Próximas", "ghost", None, lambda: self._load_rows(self._offset + PAGE_SIZE))
        pager.addWidget(self.prev_btn)
        pager.addWidget(self.next_page_btn)
        pager.addSpacing(24)
        self.discard_btn = button("Descartar importação", "danger", "trash-2", self._discard)
        pager.addWidget(self.discard_btn)
        layout.addLayout(pager)
        self._offset = 0
        self._rows = []
        return page

    def _load_review(self) -> None:
        batch = self.service.get(self.batch_id)
        if batch is None:
            return
        while self.summary_row.count():
            item = self.summary_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        counts = self.service.repo.counts_by_action(self.batch_id)
        for action in (ImportAction.CREATE, ImportAction.UPDATE, ImportAction.REVIEW, ImportAction.ERROR,
                       ImportAction.UNCHANGED, ImportAction.SKIP):
            if counts.get(action.value):
                self.summary_row.addWidget(StatusChip(action, text=f"{action.label}: {counts[action.value]}"))
        self.summary_row.addStretch(1)
        decisions = self.service.repo.counts_by_decision(self.batch_id)
        planned = decisions.get("create", 0) + decisions.get("update", 0)
        note = (f"{TARGET_LABELS.get(batch.target, batch.target)} de {batch.source_name}: "
                f"{decisions.get('create', 0)} para criar, {decisions.get('update', 0)} para atualizar, "
                f"{decisions.get('skip', 0)} ignorada(s). Nada foi gravado ainda.")
        if counts.get(ImportAction.REVIEW.value):
            note += " Linhas para revisar (extração ambígua) só entram se você incluir."
        if batch.message:
            note = batch.message + " " + note
        self.review_note.set_text(note)
        self.next_btn.setText("Confirmar importação" if planned else "Nada a gravar")
        self.next_btn.setEnabled(bool(planned) and batch.status is ImportStatus.PLANNED)
        self._load_rows(self._offset)

    def _current_filter(self):
        return FILTERS[self.filter.currentIndex()]

    def _load_rows(self, offset: int) -> None:
        if self.batch_id is None:
            return
        _, actions, only_issues = self._current_filter()
        total = self.service.count_rows(self.batch_id, actions=actions, text=self.search.text(),
                                        only_issues=only_issues)
        self._offset = max(0, min(offset, max(0, total - 1) // PAGE_SIZE * PAGE_SIZE))
        self._rows = self.service.rows(self.batch_id, actions=actions, text=self.search.text(),
                                       only_issues=only_issues, limit=PAGE_SIZE, offset=self._offset)
        self.rows_table.setRowCount(len(self._rows))
        for r, row in enumerate(self._rows):
            self.rows_table.setItem(r, 0, _item(row.data.get("where") or str(row.row_no)))
            self.rows_table.setItem(r, 1, _item(row.sku))
            self.rows_table.setItem(r, 2, _item(row.name or ("Variação de " + row.parent_sku if row.parent_sku else "")))
            status = QTableWidgetItem("")
            status.setData(Qt.ItemDataRole.UserRole, row.action.value)
            self.rows_table.setItem(r, 3, status)
            self.rows_table.setItem(r, 4, _item(DECISION_LABELS[row.decision], muted=row.decision == "skip"))
            self.rows_table.setItem(r, 5, _item(_summary(row), muted=True))
        end = self._offset + len(self._rows)
        self.page_label.setText(f"{self._offset + 1 if total else 0}–{end} de {total}")
        self.prev_btn.setEnabled(self._offset > 0)
        self.next_page_btn.setEnabled(end < total)
        self.detail.clear()

    def _selected_rows(self):
        return [self._rows[i.row()] for i in self.rows_table.selectionModel().selectedRows() if i.row() < len(self._rows)]

    def _show_detail(self) -> None:
        rows = self._selected_rows()
        if len(rows) != 1:
            self.detail.setPlainText(plural(len(rows), "linha selecionada", "linhas selecionadas") if rows else "")
            return
        row = rows[0]
        lines = [f"{row.data.get('where') or row.row_no}: {row.action.label}, decisão {DECISION_LABELS[row.decision]}"]
        if row.outcome:
            lines.append(f"Resultado: {row.outcome}")
        if row.changes:
            lines.append("")
            lines.append("Alterações (atual → arquivo):")
            lines += [f"  {c['label']}: {c['old']} → {c['new']}" for c in row.changes]
        if row.issues:
            lines.append("")
            lines.append("Problemas e avisos:")
            names = {"error": "Erro", "warning": "Aviso", "review": "Revisar"}
            lines += [f"  {names.get(i['severity'], i['severity'])}: {i['message']}" for i in row.issues]
        if row.media:
            lines.append("")
            lines.append("Imagens e arquivos:")
            states = {"found": "encontrada", "missing": "não encontrada", "external": "link externo, não baixado",
                      "ambiguous": "nome repetido em mais de uma pasta", "invalid": "inválida"}
            lines += [f"  {m['ref']}: {states.get(m['status'], m['status'])}"
                      + (" (pelo SKU no nome)" if m.get("origin") == "sku" else "") for m in row.media]
        self.detail.setPlainText("\n".join(lines))

    def _decide(self, decision: str) -> None:
        rows = self._selected_rows()
        if not rows:
            return
        try:
            if decision == "include":
                self.service.set_decision(self.batch_id, [r.id for r in rows], "create")
            else:
                self.service.set_decision(self.batch_id, [r.id for r in rows], "skip")
        except ImportProblem as exc:
            inform(self, "Não foi possível alterar", str(exc), error=True)
        self._load_review()

    def _bulk(self, action: ImportAction, decision: str) -> None:
        try:
            self.service.set_decision_for_action(self.batch_id, action, "create" if decision == "include"
                                                 else decision)
        except ImportProblem as exc:
            inform(self, "Não foi possível alterar", str(exc), error=True)
        self._load_review()

    def _export_report(self) -> None:
        default = str(self.ctx.paths.exports / f"importacao-{self.batch_id}.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Exportar relatório", default, "Planilha CSV (*.csv)")
        if path:
            count = self.service.export_report(self.batch_id, Path(path))
            show_toast(self, f"Relatório com {count} linha(s) salvo.", "success")

    def _discard(self) -> None:
        if not confirm(self, "Descartar importação", "Descartar esta importação? Nada foi gravado no catálogo; o "
                       "registro fica no histórico como descartado.", "Descartar", danger=True):
            return
        self.service.discard(self.batch_id)
        self.accept()

    # ------------------------------------------------------------------ step 5: done
    def _build_done(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(12)
        self.done_title = label("", object_name="sectionTitle")
        layout.addWidget(self.done_title)
        self.done_text = label("", wrap=True)
        layout.addWidget(self.done_text)
        layout.addWidget(label("Linhas com erro na gravação", role="muted"))
        self.errors_table = _table(["Linha", "SKU", "Resultado"])
        self.errors_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.errors_table, 1)
        row = QHBoxLayout()
        row.addWidget(button("Exportar relatório completo…", "secondary", "download", self._export_report))
        row.addStretch(1)
        layout.addLayout(row)
        return page

    def show_report(self) -> None:
        self._go(4)
        self._fill_done()

    def _fill_done(self) -> None:
        batch = self.service.get(self.batch_id)
        result = batch.counts.get("result", {})
        self.done_title.setText("Importação concluída")
        self.done_text.setText(batch.message + " Os produtos já aparecem no Catálogo; mídias pendentes ficam "
                               "marcadas em cada produto.")
        errors = [r for r in self.service.rows(self.batch_id, limit=10_000) if r.outcome.startswith("Erro")]
        self.errors_table.setRowCount(len(errors))
        for r, row in enumerate(errors):
            self.errors_table.setItem(r, 0, _item(row.data.get("where") or str(row.row_no)))
            self.errors_table.setItem(r, 1, _item(row.sku))
            self.errors_table.setItem(r, 2, _item(row.outcome))
        self.errors_table.setVisible(bool(result.get("errors")))

    # ------------------------------------------------------------------ navigation
    def _go(self, index: int) -> None:
        self._page = index
        self.stack.setCurrentIndex(index)
        self.rail.set_current(index)
        if index == 1:
            self._fill_preview()
        elif index == 2:
            self._fill_mapping()
        self._sync()

    def _sync(self, *_args) -> None:
        busy = self.runner.running
        page = self._page
        self.back_btn.setVisible(page in (1, 2))
        self.back_btn.setEnabled(not busy)
        self.close_btn.setText("Fechar" if page in (3, 4) else "Cancelar")
        self.close_btn.setEnabled(not busy)
        hint = ""
        if page == 0:
            ready = self.analysis is not None and not self.analysis.needs_table_choice
            self.next_btn.setText("Analisar imagens" if ready and self.analysis.images_only else "Avançar")
            self.next_btn.setEnabled(ready and not busy)
        elif page == 1:
            self.next_btn.setText("Avançar")
            self.next_btn.setEnabled(not busy)
        elif page == 2:
            problems = mapping_problems(self.mapping(), self.analysis.target) if self.analysis else []
            needs = not self.confirm_probable.isHidden() and not self.confirm_probable.isChecked()
            hint = problems[0] if problems else ("Confirme os campos prováveis para continuar." if needs else
                                                 "A análise valida cada linha e não grava nada.")
            self.next_btn.setText("Analisar e revisar")
            self.next_btn.setEnabled(not problems and not needs and not busy)
        elif page == 3:
            hint = "Confira as alterações antes de confirmar. A gravação é feita de uma vez: se cancelar, nada muda."
            self.next_btn.setEnabled(self.next_btn.isEnabled() and not busy)
            self.discard_btn.setEnabled(not busy)
        elif page == 4:
            self.next_btn.setText("Abrir catálogo")
            self.next_btn.setEnabled(True)
        self.footer_hint.setText(hint)

    def _back(self) -> None:
        if self._page == 2 and self.analysis and self.analysis.images_only:
            self._go(0)
        elif self._page > 0:
            self._go(self._page - 1)

    def _next(self) -> None:
        if self._page == 0:
            if self.analysis.images_only:
                self._start_plan()  # no table to preview or map: straight to the review
            else:
                self._go(1)
        elif self._page == 1:
            self._go(2)
        elif self._page == 2:
            self._start_plan()
        elif self._page == 3:
            self._start_commit()
        elif self._page == 4:
            self.accept()

    # ------------------------------------------------------------------ background work
    def _busy(self, on: bool, text: str = "") -> None:
        self.progress_row.setVisible(on)
        self.progress_text.setText(text)
        self.progress_bar.setRange(0, 0)
        self._sync()

    def _on_progress(self, done: int, total: int, message: str) -> None:
        self.progress_text.setText(message)
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(min(done, total))
        else:
            self.progress_bar.setRange(0, 0)

    def _task_done(self, result) -> None:
        if self._task == "plan":
            self._planned(result)
        else:
            self._committed(result)

    def _start_plan(self) -> None:
        analysis, mapping, options = self.analysis, self.mapping(), self.options()
        self._task = "plan"
        self._busy(True, "Analisando o arquivo…")
        self.runner.start(lambda report, cancel: self.service.plan(analysis, mapping, options, report, cancel))

    def _planned(self, batch) -> None:
        self._busy(False)
        self.batch_id = batch.id
        self.analysis = None  # staging now belongs to the batch
        self._go(3)
        self._load_review()

    def _start_commit(self) -> None:
        decisions = self.service.repo.counts_by_decision(self.batch_id)
        text = (f"Gravar {decisions.get('create', 0)} novo(s) e atualizar {decisions.get('update', 0)} registro(s) "
                "no catálogo? Os dados atuais que mudam estão listados na revisão. Você pode cancelar durante a "
                "gravação sem alterar nada.")
        if not confirm(self, "Confirmar importação", text, "Gravar no catálogo"):
            return
        self._task = "commit"
        self._busy(True, "Gravando no catálogo…")
        batch_id = self.batch_id
        self.runner.start(lambda report, cancel: self.service.commit(batch_id, report, cancel))

    def _committed(self, _report) -> None:
        self._busy(False)
        self.changed_catalog = True
        self._go(4)
        self._fill_done()

    def _task_failed(self, message: str) -> None:
        self._busy(False)
        inform(self, "A operação não foi concluída", message, error=True)
        if self.batch_id is not None and self._page == 3:
            self._load_review()

    def _task_cancelled(self) -> None:
        self._busy(False)
        show_toast(self, "Análise cancelada; nada foi gravado." if self._task == "plan" else
                   "Gravação cancelada; nenhuma alteração foi feita.", "warning")
        if self.batch_id is not None and self._page == 3:
            self._load_review()

    def _cancel_task(self) -> None:
        self.runner.cancel()
        self.progress_text.setText("Cancelando…")

    # ------------------------------------------------------------------ closing
    def _discard_analysis(self) -> None:
        if self.analysis is not None and self.batch_id is None:
            self.service.discard_analysis(self.analysis)
        self.analysis = None

    def reject(self) -> None:
        if self.runner.running:
            return
        self._discard_analysis()
        super().reject()

    def accept(self) -> None:
        self._discard_analysis()
        super().accept()


def _summary(row) -> str:
    parts = []
    if row.outcome:
        parts.append(row.outcome)
    if row.changes:
        parts.append(", ".join(c["label"] for c in row.changes[:4]) + ("…" if len(row.changes) > 4 else ""))
    issues = [i["message"] for i in row.issues if i["severity"] in ("error", "review")] or \
        [i["message"] for i in row.issues]
    if issues:
        parts.append(issues[0] + (f" (+{len(issues) - 1})" if len(issues) > 1 else ""))
    images = sum(1 for m in row.media if m["status"] == "found")
    if images:
        parts.append(plural(images, "imagem", "imagens"))
    return "  |  ".join(parts)


# ---------------------------------------------------------------------------- page
class ImportsPage(Page):
    key = "imports"
    title = "Central de Importações"
    subtitle = "Traga a base de produtos da empresa: planilhas, XML, JSON, PDF e ZIP com fotos."

    def __init__(self, ctx, navigate, parent=None):
        super().__init__(ctx, navigate, parent)
        self.header.add_action(button("Associar imagens de uma pasta…", "secondary", "folder-input",
                                      self._folder))
        self.header.add_action(button("Nova importação", "primary", "file-up", lambda: self.open_wizard()))
        bar = QHBoxLayout()
        self.count_label = label("", role="hint")
        bar.addWidget(self.count_label, 1)
        self.continue_btn = button("Revisar e confirmar", "secondary", "list-checks", self._continue)
        self.report_btn = button("Ver relatório", "ghost", "file-text", self._continue)
        self.discard_btn = button("Descartar", "danger", "trash-2", self._discard)
        for b in (self.continue_btn, self.report_btn, self.discard_btn):
            bar.addWidget(b)
        self.root.addLayout(bar)
        self.table = _table(["Data", "Arquivo", "Tipo", "Situação", "Resultado"])
        self.table.setItemDelegateForColumn(3, StatusDelegate(self.table, ImportStatus))
        h = self.table.horizontalHeader()
        for col, width in ((0, 130), (1, 280), (2, 140), (3, 200)):
            h.resizeSection(col, width)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self._sync)
        self.table.doubleClicked.connect(lambda _i: self._continue())
        self.empty = EmptyState("file-up", "Nenhuma importação ainda",
                                "Importe a planilha ou o catálogo do cliente. Você revisa tudo antes de gravar.",
                                button("Nova importação", "primary", "file-up", lambda: self.open_wizard()))
        holder = QFrame()
        stack = QVBoxLayout(holder)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.addWidget(self.table, 1)
        stack.addWidget(self.empty, 1)
        self.root.addWidget(holder, 1)
        self._batches = []
        self._sync()

    def refresh(self) -> None:
        self._batches = self.ctx.imports.history(200)
        self.table.setRowCount(len(self._batches))
        for r, batch in enumerate(self._batches):
            self.table.setItem(r, 0, _item(format_when(batch.created_at)))
            self.table.setItem(r, 1, _item(batch.source_name))
            self.table.setItem(r, 2, _item(f"{TARGET_LABELS.get(batch.target, batch.target)}, "
                                           f"{FORMAT_LABELS.get(batch.format, 'pasta').split(' ')[0]}", muted=True))
            status = QTableWidgetItem("")
            status.setData(Qt.ItemDataRole.UserRole, batch.status.value)
            self.table.setItem(r, 3, status)
            self.table.setItem(r, 4, _item(batch.message or _planned_text(batch), muted=True))
        self.table.setVisible(bool(self._batches))
        self.empty.setVisible(not self._batches)
        pending = sum(1 for b in self._batches if b.status is ImportStatus.PLANNED)
        self.header.set_subtitle(f"{plural(len(self._batches), 'importação no histórico', 'importações no histórico')}"
                                 + (f", {pending} aguardando sua confirmação" if pending else ""))
        self._sync()

    def open_with(self, path: str | None = None, target: str = "products", wizard: bool = False, **_) -> None:
        if path or wizard:
            QTimer.singleShot(0, lambda: self.open_wizard(Path(path) if path else None, target))

    def _selected(self):
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        return self._batches[rows[0].row()] if rows and rows[0].row() < len(self._batches) else None

    def _sync(self) -> None:
        batch = self._selected()
        planned = batch is not None and batch.status is ImportStatus.PLANNED
        done = batch is not None and batch.status is ImportStatus.COMPLETED
        self.continue_btn.setVisible(planned)
        self.discard_btn.setVisible(planned)
        self.report_btn.setVisible(done)
        self.count_label.setText("Selecione uma importação para revisar, confirmar ou ver o relatório."
                                 if self._batches else "")

    def open_wizard(self, path: Path | None = None, target: str = "products", batch_id: int | None = None) -> None:
        wizard = ImportWizard(self.ctx, self, batch_id=batch_id, path=path, target=target)
        wizard.target.setCurrentIndex(max(0, wizard.target.findData(target)))
        wizard.exec()
        self.refresh()
        if wizard.changed_catalog:
            show_toast(self, "Importação gravada no catálogo.", "success")

    def _folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Pasta com as fotos dos produtos")
        if folder:
            self.open_wizard(Path(folder))

    def _continue(self) -> None:
        batch = self._selected()
        if batch is None:
            return
        if batch.status in (ImportStatus.PLANNED, ImportStatus.COMPLETED):
            wizard = ImportWizard(self.ctx, self, batch_id=batch.id)
            if batch.status is ImportStatus.COMPLETED:
                wizard.show_report()
            wizard.exec()
            self.refresh()

    def _discard(self) -> None:
        batch = self._selected()
        if batch is None or not confirm(self, "Descartar importação", f"Descartar a importação de "
                                        f"{batch.source_name}? Nada foi gravado no catálogo.", "Descartar",
                                        danger=True):
            return
        self.ctx.imports.discard(batch.id)
        self.refresh()


def _planned_text(batch) -> str:
    planned = batch.counts.get("planned", {})
    if not planned:
        return ""
    names = {"create": "novo(s)", "update": "atualização(ões)", "error": "com erro", "review": "para revisar",
             "unchanged": "sem mudanças", "skip": "ignorada(s)"}
    return ", ".join(f"{n} {names.get(k, k)}" for k, n in planned.items())


__all__ = ["ImportWizard", "ImportsPage"]
