"""Version, folders and updates (GitHub Releases feed, verified download, installer after closing)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QPlainTextEdit, QProgressBar

from mla import __version__
from mla.config.paths import AppPaths
from mla.services.updates import UpdateCancelled, UpdateError, UpdateService
from mla.ui.pages.base import Page
from mla.ui.widgets.common import Callout, Panel, StatusChip, button, confirm, inform, label, show_toast
from mla.ui.workers import TaskRunner


def installed_app() -> bool:
    return bool(getattr(sys, "frozen", False))


class UpdatesPage(Page):
    key = "updates"
    title = "Versão e atualizações"
    subtitle = "Versão instalada, pastas do programa e dos dados e novas versões."

    def __init__(self, ctx, navigate, parent=None, service: UpdateService | None = None):
        super().__init__(ctx, navigate, parent)
        self.service = service or UpdateService(AppPaths.default().root)
        self.release = None
        self.runner = TaskRunner(self, cancelled_types=(UpdateCancelled,))
        self.runner.progress.connect(self._progress)
        self.runner.finished.connect(self._task_done)
        self.runner.failed.connect(self._task_failed)
        self.runner.cancelled.connect(lambda: self._set_status("Download cancelado.", "neutral"))
        self._task = ""

        about = Panel("Esta instalação")
        head = QHBoxLayout()
        head.addWidget(label(f"MLA {__version__}", object_name="sectionTitle"), 1)
        head.addWidget(StatusChip(text="Beta" if "-" in __version__ else "Versão estável",
                                  tone="warning" if "-" in __version__ else "success"))
        about.body.addLayout(head)
        program = Path(sys.executable).parent if installed_app() else Path(__file__).resolve().parents[3]
        where = "Programa instalado em" if installed_app() else "Executando a partir do código-fonte em"
        for text in (f"{where}: {program}", f"Dados desta empresa: {ctx.paths.root}",
                     f"Downloads de atualização: {self.service.folder}"):
            line = label(text, role="muted", wrap=True)
            line.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            about.add(line)
        folders = QHBoxLayout()
        folders.addWidget(button("Abrir pasta de dados", "ghost", "folder-open", lambda: self._open(ctx.paths.root)))
        folders.addWidget(button("Abrir pasta de logs", "ghost", "file-text", lambda: self._open(ctx.paths.logs)))
        folders.addStretch(1)
        about.body.addLayout(folders)
        self.root.addWidget(about)

        updates = Panel("Atualizações")
        channel = label(f"Canal: {self.service.feed_url}", role="hint", wrap=True)
        channel.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        updates.add(channel)
        status_row = QHBoxLayout()
        self.status_chip = StatusChip(text="Não verificado", tone="neutral")
        status_row.addWidget(self.status_chip)
        self.status = label("Clique em Verificar agora.", role="muted", wrap=True)
        status_row.addWidget(self.status, 1)
        updates.body.addLayout(status_row)
        self.bar = QProgressBar()
        self.bar.setFixedHeight(6)
        self.bar.setTextVisible(False)
        self.bar.setVisible(False)
        updates.add(self.bar)
        self.notes = QPlainTextEdit()
        self.notes.setReadOnly(True)
        self.notes.setMaximumHeight(160)
        self.notes.setVisible(False)
        updates.add(self.notes)
        self.note = Callout()
        self.note.set_text("" if installed_app() else
                           "Instalar atualizações só funciona no programa instalado (MLA-Setup). Aqui é possível "
                           "apenas verificar.")
        updates.add(self.note)
        actions = QHBoxLayout()
        self.check_btn = button("Verificar agora", "secondary", "refresh-cw", self.check)
        self.install_btn = button("Baixar e instalar", "primary", "download", self._download)
        self.install_btn.setVisible(False)
        self.cancel_btn = button("Cancelar", "ghost", None, self.runner.cancel)
        self.cancel_btn.setVisible(False)
        for b in (self.check_btn, self.install_btn, self.cancel_btn):
            actions.addWidget(b)
        actions.addStretch(1)
        updates.body.addLayout(actions)
        updates.add(label("O instalador baixado é conferido pelo código SHA-256 publicado com a versão. Seus dados "
                          "(catálogo, contas, configurações, fila e histórico) ficam fora da pasta do programa e são "
                          "mantidos. Antes de atualizar o banco, o MLA faz um backup.", role="hint", wrap=True))
        self.root.addWidget(updates)
        self.root.addStretch(1)
        if installed_app():
            self.service.cleanup()  # installers of versions already applied (each is ~130 MB)
        if installed_app() and os.environ.get("MLA_NO_UPDATE_CHECK") != "1":
            QTimer.singleShot(8000, lambda: self.check(quiet=True))

    # ------------------------------------------------------------------ actions
    @staticmethod
    def _open(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _set_status(self, text: str, tone: str, chip: str = "") -> None:
        self.status.setText(text)
        self.status_chip.set_status(text=chip or {"success": "Atualizado", "warning": "Disponível",
                                                  "danger": "Falha"}.get(tone, "Não verificado"), tone=tone)
        self.check_btn.setEnabled(not self.runner.running)
        self.cancel_btn.setVisible(self.runner.running and self._task == "download")
        self.bar.setVisible(self.runner.running)

    def check(self, quiet: bool = False) -> None:
        if self.runner.running:
            return
        self._task = "check-quiet" if quiet else "check"
        self.check_btn.setEnabled(False)
        self.status.setText("Consultando o canal de atualizações…")
        self.runner.start(lambda _progress, _cancel: self.service.check())

    def _download(self) -> None:
        if self.release is None or self.runner.running:
            return
        if not installed_app():
            inform(self, "Atualização", "Instale o MLA pelo MLA-Setup para receber atualizações automáticas.")
            return
        self._task = "download"
        self.install_btn.setEnabled(False)
        self.bar.setRange(0, 1000)
        self.bar.setValue(0)
        self._set_status(f"Baixando a versão {self.release.version}…", "warning", "Baixando")
        release = self.release
        self.runner.start(lambda progress, cancel: self.service.download(
            release, lambda done, total: progress(done, total, ""), cancel))

    def _progress(self, done: int, total: int, _message: str) -> None:
        if total > 0:
            self.bar.setValue(int(1000 * done / total))
            self.status.setText(f"Baixando: {done / 1024 ** 2:.1f} de {total / 1024 ** 2:.1f} MB")

    def _task_done(self, result) -> None:
        task, self._task = self._task, ""
        if task.startswith("check"):
            self.release = result.latest if result.available else None
            if result.available:
                self._set_status(result.message, "warning")
                self.notes.setPlainText(result.latest.notes or "(sem notas da versão)")
                self.notes.setVisible(True)
                self.install_btn.setVisible(True)
                self.install_btn.setEnabled(installed_app())
                if task == "check-quiet":
                    show_toast(self.window(), f"Nova versão do MLA disponível ({result.latest.version}). "
                                              "Veja em Atualizações.", "warning")
            else:
                self._set_status(result.message, "success" if result.latest else "neutral",
                                 "Atualizado" if result.latest else "Sem versões")
            return
        self._set_status(f"Versão {self.release.version} baixada e conferida.", "success", "Pronto")
        self._install(result)

    def _task_failed(self, message: str) -> None:
        task, self._task = self._task, ""
        if task == "check-quiet":
            self._set_status(f"Verificação automática não concluída: {message}", "neutral")
            return
        self._set_status(message, "danger")
        self.install_btn.setEnabled(self.release is not None and installed_app())

    def _install(self, setup: Path) -> None:
        window = self.window()
        executor = getattr(getattr(window, "services", None), "executor", None)
        if executor is not None and executor.current_item is not None:
            inform(self, "Atualização", "Há um anúncio em execução. Aguarde terminar e clique em Baixar e instalar "
                                        "de novo (o arquivo já baixado será conferido outra vez).")
            self.install_btn.setEnabled(True)
            return
        if not confirm(self, "Instalar atualização", f"O MLA vai fechar, instalar a versão {self.release.version} "
                       "e abrir de novo. Seus dados são mantidos. Continuar?", "Fechar e atualizar"):
            self.install_btn.setEnabled(True)
            return
        try:
            self.service.launch_installer(setup)
        except (OSError, UpdateError) as exc:
            inform(self, "Atualização", f"Não foi possível iniciar o instalador: {exc}", error=True)
            return
        window.close()
