from __future__ import annotations

from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QGridLayout, QHBoxLayout, QHeaderView, QListWidget, QProgressBar,
    QSplitter, QStackedLayout, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from mla.automation.base import FORM_STEPS
from mla.automation.executor import Decision, ReviewRequest
from mla.core.enums import CatalogStatus, ItemStatus, JobStatus
from mla.persistence.repositories import ProductQuery
from mla.ui.pages.base import Page
from mla.ui.pages.history import STEP_LABELS
from mla.ui.theme import T
from mla.ui.widgets.common import (
    Panel, StatusChip, StatusDelegate, button, clear_layout, format_when, inform, label, plural,
    show_toast, thumbnail,
)

ALL_STEPS = ["validate", "duplicates", "open_browser", "login", "open_form", *[k for k, _ in FORM_STEPS],
             "review", "await_approval", "publish", "confirm"]
JOB_TONE = {JobStatus.PENDING: "violet", JobStatus.RUNNING: "active", JobStatus.PAUSED: "warning",
            JobStatus.COMPLETED: "success", JobStatus.CANCELLED: "muted"}
FORM_LABELS = {"title": "Título", "price": "Preço", "stock": "Estoque", "images": "Fotos", "category": "Categoria",
               "description": "Descrição"}


class AutomationsPage(Page):
    key = "automations"
    title = "Automações"
    subtitle = "Um item por vez. Nada é publicado sem a sua aprovação."

    def __init__(self, ctx, navigate, services, parent=None):
        self.services = services
        super().__init__(ctx, navigate, parent)
        self._review: ReviewRequest | None = None
        self._manual_item = None
        self.header.add_action(button("Executar produtos prontos", "secondary", "play", self._run_all_ready))

        self.root.addWidget(self._build_now())
        self.root.addWidget(self._build_queue(), 1)
        self._now_mode("idle")

        bridge = services.bridge
        bridge.itemStarted.connect(self._on_started)
        bridge.stepChanged.connect(self._on_step)
        bridge.itemFinished.connect(self._on_finished)
        bridge.reviewRequested.connect(self._on_review)
        bridge.manualActionRequested.connect(self._on_manual)
        bridge.logAdded.connect(self._on_log)
        self._timer = QTimer(self, interval=4000, timeout=self._refresh_jobs)

    # ------------------------------------------------------------------ layout
    def _now_mode(self, mode: str) -> None:
        """Keep the 'Agora' panel compact when idle so the queue gets the space."""
        self.now.setMaximumHeight({"idle": 104, "running": 230}.get(mode, 16777215))

    def _build_now(self) -> QWidget:
        self.now = Panel("Agora")
        self.now_stack = QStackedLayout()
        holder = QWidget()
        holder.setLayout(self.now_stack)
        self.now.add(holder)
        idle = label("Nenhuma execução em andamento. Use Executar em Produtos ou em Grupos: cada anúncio é "
                     "preenchido no navegador e para aqui para você conferir antes de publicar.", role="muted",
                     wrap=True)
        self.now_stack.addWidget(idle)

        running = QWidget()
        lay = QVBoxLayout(running)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        top = QHBoxLayout()
        self.run_title = label("", object_name="sectionTitle")
        top.addWidget(self.run_title, 1)
        self.run_chip = StatusChip(ItemStatus.RUNNING)
        top.addWidget(self.run_chip)
        top.addWidget(button("Cancelar item", "danger", "x", self._cancel_current))
        lay.addLayout(top)
        self.run_meta = label("", role="muted")
        lay.addWidget(self.run_meta)
        self.progress = QProgressBar()
        self.progress.setMaximum(len(ALL_STEPS))
        self.progress.setFixedHeight(6)
        lay.addWidget(self.progress)
        self.run_step = label("", role="hint")
        lay.addWidget(self.run_step)
        self.manual_box = QWidget()
        manual = QHBoxLayout(self.manual_box)
        manual.setContentsMargins(12, 10, 12, 10)
        self.manual_box.setStyleSheet(f"background: {T.warning_wash}; border-radius: 8px;")
        self.manual_text = label("", wrap=True)
        self.manual_text.setStyleSheet(f"color: {T.warning}; background: transparent;")
        manual.addWidget(self.manual_text, 1)
        manual.addWidget(button("Continuar", "primary", "check", self._continue_manual))
        self.manual_box.hide()
        lay.addWidget(self.manual_box)
        self.now_stack.addWidget(running)

        review = QWidget()
        rlay = QHBoxLayout(review)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.setSpacing(18)
        self.shot = label("")
        self.shot.setFixedSize(260, 200)
        self.shot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.shot.setStyleSheet(f"background: {T.canvas}; border: 1px solid {T.line}; border-radius: 8px;")
        self.shot.setCursor(Qt.CursorShape.PointingHandCursor)
        self.shot.setToolTip("Abrir captura do formulário preenchido")
        self.shot.mousePressEvent = lambda _e: self._open_shot()
        rlay.addWidget(self.shot, 0, Qt.AlignmentFlag.AlignTop)
        info = QVBoxLayout()
        info.setSpacing(6)
        head = QHBoxLayout()
        self.review_title = label("", object_name="sectionTitle")
        head.addWidget(self.review_title, 1)
        head.addWidget(StatusChip(ItemStatus.AWAITING_REVIEW))
        info.addLayout(head)
        info.addWidget(label("Confira o formulário no navegador. Você pode corrigir algo por lá antes de aprovar.",
                             role="muted", wrap=True))
        self.review_grid = QGridLayout()
        self.review_grid.setHorizontalSpacing(16)
        self.review_grid.setVerticalSpacing(4)
        info.addLayout(self.review_grid)
        self.review_notes = label("", wrap=True)
        info.addWidget(self.review_notes)
        info.addStretch(1)
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(button("Rejeitar", "danger", "x", lambda: self._decide(Decision.REJECT)))
        self.approve_btn = button("Aprovar e publicar", "success", "check", lambda: self._decide(Decision.APPROVE))
        actions.addWidget(self.approve_btn)
        info.addLayout(actions)
        rlay.addLayout(info, 1)
        self.now_stack.addWidget(review)
        return self.now

    def _build_queue(self) -> QWidget:
        panel = Panel("Fila e execuções")
        tools = QHBoxLayout()
        self.pause_btn = button("Pausar", "ghost", "pause", self._pause)
        self.resume_btn = button("Retomar", "ghost", "play", self._resume)
        self.cancel_btn = button("Cancelar execução", "danger", "square", self._cancel_job)
        for b in (self.pause_btn, self.resume_btn, self.cancel_btn):
            tools.addWidget(b)
        tools.addStretch(1)
        self.queue_hint = label("", role="hint")
        tools.addWidget(self.queue_hint)
        panel.body.addLayout(tools)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setHandleWidth(12)
        self.jobs = QTableWidget(0, 3)
        self.jobs.setHorizontalHeaderLabels(["Execução", "Status", "Progresso"])
        self._table_style(self.jobs)
        self.jobs.setItemDelegateForColumn(1, StatusDelegate(self.jobs, JobStatus, JOB_TONE))
        self.jobs.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col, width in ((1, 118), (2, 76)):
            self.jobs.horizontalHeader().resizeSection(col, width)
        self.jobs.itemSelectionChanged.connect(self._on_job_selected)
        split.addWidget(self.jobs)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.items = QTableWidget(0, 5)
        self.items.setHorizontalHeaderLabels(["Produto", "Marketplace", "Status", "Etapa", "Observação"])
        self._table_style(self.items)
        self.items.setItemDelegateForColumn(2, StatusDelegate(self.items, ItemStatus))
        self.items.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col, width in ((1, 140), (2, 160), (3, 100), (4, 130)):
            self.items.horizontalHeader().resizeSection(col, width)
        rl.addWidget(self.items, 2)
        rl.addWidget(label("Registro ao vivo", role="muted"))
        self.live_log = QListWidget()
        self.live_log.setMaximumHeight(140)
        rl.addWidget(self.live_log, 1)
        split.addWidget(right)
        split.setSizes([400, 780])
        panel.add(split, 1)
        return panel

    @staticmethod
    def _table_style(table: QTableWidget) -> None:
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(40)
        table.setShowGrid(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        table.setWordWrap(False)
        table.setTextElideMode(Qt.TextElideMode.ElideRight)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    # ------------------------------------------------------------------ page lifecycle
    def refresh(self) -> None:
        self._refresh_jobs()
        self._timer.start()

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def open_with(self, run_products: list[int] | None = None, run_group: int | None = None,
                  rerun_item: int | None = None, **_):
        queue = self.services.queue
        result = None
        if run_products:
            result = queue.enqueue(run_products)
        elif run_group is not None:
            group = self.ctx.groups.get(run_group)
            if group:
                result = queue.enqueue_group(group)
        elif rerun_item is not None:
            result = queue.requeue_item(rerun_item)
        if result is None:
            return
        self._report(result)
        if result.queued:
            self.services.executor.wake()
        self._refresh_jobs()

    def _report(self, result) -> None:
        if result.queued and not result.skipped:
            show_toast(self, f"{result.queued} anúncio(s) na fila", "success")
            return
        lines = [f"{s.product_name}" + (f" ({s.marketplace.label})" if s.marketplace else "") + f": {s.reason}"
                 for s in result.skipped[:12]]
        more = len(result.skipped) - 12
        text = (f"{result.queued} anúncio(s) entraram na fila.\n\nNão incluídos:\n" + "\n".join(lines)
                + (f"\n… e mais {more}" if more > 0 else ""))
        inform(self, "Resultado da execução", text, error=not result.queued)

    def _run_all_ready(self) -> None:
        ids = [p.id for p in self.ctx.catalog.search(ProductQuery(status=CatalogStatus.READY))]
        if not ids:
            inform(self, "Nada para executar", "Nenhum produto está pronto. Complete os cadastros em Produtos.")
            return
        self.open_with(run_products=ids)

    # ------------------------------------------------------------------ jobs table
    def _refresh_jobs(self) -> None:
        selected = self._selected_job_id()
        jobs = self.ctx.automation_repo.list_jobs(limit=100)
        self.jobs.setRowCount(len(jobs))
        for row, job in enumerate(jobs):
            items = self.ctx.automation_repo.items_for_job(job.id)
            done = sum(1 for i in items if i.status.is_terminal)
            cells = [job.label, "", f"{done}/{len(items)}"]
            for col, value in enumerate(cells):
                cell = QTableWidgetItem(value)
                cell.setData(Qt.ItemDataRole.UserRole, job.id if col == 0 else (job.status if col == 1 else None))
                cell.setToolTip(f"{job.label}\nCriada {format_when(job.created_at)}")
                if col == 2:
                    cell.setForeground(QColor(T.text_2))
                self.jobs.setItem(row, col, cell)
            if job.id == selected:
                self.jobs.selectRow(row)
        if self.jobs.rowCount() and not self.jobs.selectedItems():
            self.jobs.selectRow(0)
        active = [j for j in jobs if j.status in (JobStatus.PENDING, JobStatus.RUNNING)]
        self.queue_hint.setText(plural(len(active), "execução ativa", "execuções ativas") if active
                                else "Nada na fila")
        self._on_job_selected()

    def _selected_job_id(self) -> int | None:
        rows = self.jobs.selectionModel().selectedRows() if self.jobs.selectionModel() else []
        if not rows:
            return None
        return self.jobs.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)

    def _on_job_selected(self) -> None:
        job_id = self._selected_job_id()
        job = self.ctx.automation_repo.get_job(job_id) if job_id else None
        self.pause_btn.setEnabled(bool(job and job.status in (JobStatus.PENDING, JobStatus.RUNNING)))
        self.resume_btn.setEnabled(bool(job and job.status is JobStatus.PAUSED))
        self.cancel_btn.setEnabled(bool(job and job.status not in (JobStatus.COMPLETED, JobStatus.CANCELLED)))
        items = self.ctx.automation_repo.items_for_job(job_id) if job_id else []
        self.items.setRowCount(len(items))
        for row, item in enumerate(items):
            note = item.error or item.external_id
            cells = [item.product_name, item.marketplace.label, "", STEP_LABELS.get(item.step, item.step), note]
            for col, value in enumerate(cells):
                cell = QTableWidgetItem(value)
                if col == 2:
                    cell.setData(Qt.ItemDataRole.UserRole, item.status)
                if col == 4 and item.error:
                    cell.setForeground(QColor(T.danger))
                    cell.setToolTip(item.error)
                self.items.setItem(row, col, cell)

    def _pause(self) -> None:
        if (job_id := self._selected_job_id()) is not None:
            self.services.queue.pause(job_id)
            show_toast(self, "Pausado: o item em andamento termina e a fila para.")
            self._refresh_jobs()

    def _resume(self) -> None:
        if (job_id := self._selected_job_id()) is not None:
            self.services.queue.resume(job_id)
            self.services.executor.wake()
            self._refresh_jobs()

    def _cancel_job(self) -> None:
        if (job_id := self._selected_job_id()) is None:
            return
        running = self.services.queue.cancel(job_id)
        self.services.executor.cancel_items(running)
        self._refresh_jobs()

    # ------------------------------------------------------------------ live execution
    def _on_started(self, item) -> None:
        self.now_stack.setCurrentIndex(1)
        self._now_mode("running")
        self.manual_box.hide()
        self.run_title.setText(item.product_name)
        self.run_meta.setText(f"{item.marketplace.label}, conta {item.account_label or item.account_id}, "
                              f"tentativa {item.attempts}")
        self.run_chip.set_status(ItemStatus.RUNNING)
        self.live_log.clear()
        self._refresh_jobs()

    def _on_step(self, item, step: str) -> None:
        if step in ALL_STEPS:
            self.progress.setValue(ALL_STEPS.index(step) + 1)
        self.run_step.setText(f"Etapa: {STEP_LABELS.get(step, step)}")

    def _on_log(self, entry) -> None:
        if not entry.message:
            return
        self.live_log.addItem(f"{entry.created_at[11:19]}  {entry.message}")
        row = self.live_log.count() - 1
        color = {"ERROR": T.danger, "WARNING": T.warning}.get(entry.level)
        if color:
            self.live_log.item(row).setForeground(QColor(color))
        self.live_log.scrollToBottom()

    def _on_manual(self, item, message: str) -> None:
        self._manual_item = item
        self.manual_text.setText(message)
        self.manual_box.show()
        self.run_chip.set_status(text="Aguardando você", tone="warning")
        QApplication.alert(self.window())
        show_toast(self, "O navegador precisa de você: " + message, "warning")

    def _continue_manual(self) -> None:
        if self._manual_item:
            self.services.executor.decide(self._manual_item.id, Decision.CONTINUE)
            self.manual_box.hide()
            self.run_chip.set_status(ItemStatus.RUNNING)
            self._manual_item = None

    def _on_review(self, request: ReviewRequest) -> None:
        self._review = request
        self.now_stack.setCurrentIndex(2)
        self._now_mode("review")
        self.review_title.setText(f"{request.item.product_name} no {request.item.marketplace.label}")
        clear_layout(self.review_grid)
        for row, (key, caption) in enumerate(FORM_LABELS.items()):
            value = request.form.get(key, "")
            if key == "description":
                value = f"{len(value)} caracteres"
            self.review_grid.addWidget(label(caption, role="muted"), row, 0)
            self.review_grid.addWidget(label(value[:90]), row, 1)
        notes = []
        if request.mismatches:
            notes.append("Divergências: " + "; ".join(str(m) for m in request.mismatches))
        notes += request.warnings[:3]
        self.review_notes.setText("\n".join(notes))
        self.review_notes.setStyleSheet(f"color: {T.warning};" if notes else "")
        pm = thumbnail(self.ctx.paths.artifacts / request.screenshot, 200) if request.screenshot else None
        if pm is not None and not pm.isNull():
            self.shot.setPixmap(pm.scaled(self.shot.size() * 2, Qt.AspectRatioMode.KeepAspectRatio,
                                          Qt.TransformationMode.SmoothTransformation))
        else:
            self.shot.setText("Sem captura")
        QApplication.alert(self.window())
        self._refresh_jobs()

    def _open_shot(self) -> None:
        if self._review and self._review.screenshot:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.ctx.paths.artifacts / self._review.screenshot)))

    def _decide(self, decision: Decision) -> None:
        if self._review and self.services.executor.decide(self._review.item.id, decision):
            self.now_stack.setCurrentIndex(1)
            self.run_chip.set_status(text="Publicando" if decision is Decision.APPROVE else "Encerrando",
                                     tone="active")
            self._review = None

    def _cancel_current(self) -> None:
        item = self.services.executor.current_item
        if item:
            self.services.executor.decide(item.id, Decision.CANCEL)

    def _on_finished(self, item, status, message: str) -> None:
        self.now_stack.setCurrentIndex(0)
        self._now_mode("idle")
        self.manual_box.hide()
        tone = {ItemStatus.PUBLISHED: "success", ItemStatus.FAILED: "danger",
                ItemStatus.NEEDS_ATTENTION: "danger"}.get(status, "neutral")
        text = f"{item.product_name}: {status.label}" + (f". {message}" if message else "")
        show_toast(self, text[:220], tone)
        self._refresh_jobs()
