from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QListWidget, QListWidgetItem, QScrollArea, QSpinBox,
    QVBoxLayout, QWidget,
)

from mla import __version__
from mla.persistence.backup import create_backup, list_backups, restore_backup
from mla.services.settings import BROWSER_CHANNELS
from mla.ui.pages.base import Page
from mla.ui.widgets.common import Panel, button, confirm, inform, label, show_toast


class SettingsPage(Page):
    key = "settings"
    title = "Configurações"

    def __init__(self, ctx, navigate, on_restore=None, parent=None):
        super().__init__(ctx, navigate, parent)
        self.on_restore = on_restore
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        col = QVBoxLayout(body)
        col.setContentsMargins(0, 0, 8, 0)
        col.setSpacing(16)
        scroll.setWidget(body)
        self.root.addWidget(scroll, 1)

        automation = Panel("Automação")
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)
        self.channel = QComboBox()
        for key, text in BROWSER_CHANNELS.items():
            self.channel.addItem(text, key)
        self.channel.currentIndexChanged.connect(lambda: self._set("browser.channel", self.channel.currentData()))
        grid.addWidget(label("Navegador", role="muted"), 0, 0)
        grid.addWidget(self.channel, 0, 1)
        self.timeout = QSpinBox()
        self.timeout.setRange(5, 300)
        self.timeout.setSuffix(" s")
        self.timeout.valueChanged.connect(lambda v: self._set("automation.step_timeout_s", v))
        grid.addWidget(label("Tempo máximo por etapa", role="muted"), 1, 0)
        grid.addWidget(self.timeout, 1, 1)
        self.retries = QSpinBox()
        self.retries.setRange(0, 5)
        self.retries.valueChanged.connect(lambda v: self._set("automation.max_retries", v))
        grid.addWidget(label("Novas tentativas por etapa", role="muted"), 2, 0)
        grid.addWidget(self.retries, 2, 1)
        self.shots = QCheckBox("Salvar captura de tela quando uma etapa falhar")
        self.shots.toggled.connect(lambda v: self._set("automation.screenshot_on_failure", v))
        grid.addWidget(self.shots, 3, 0, 1, 2)
        grid.setColumnStretch(2, 1)
        automation.body.addLayout(grid)
        automation.add(label("O Microsoft Edge já vem com o Windows e é o recomendado. Cada conta usa um perfil "
                             "próprio; o navegador pessoal nunca é lido.", role="hint", wrap=True))
        col.addWidget(automation)

        data = Panel("Dados e backups")
        data.add(label(f"Pasta de dados: {ctx.paths.root}", role="muted", wrap=True))
        row = QHBoxLayout()
        row.addWidget(button("Abrir pasta de dados", "secondary", "folder-open",
                             lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(ctx.paths.root)))))
        row.addWidget(button("Abrir logs", "ghost", "file-text",
                             lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(ctx.paths.logs)))))
        row.addStretch(1)
        data.body.addLayout(row)
        self.auto_backup = QCheckBox("Criar um backup ao abrir o aplicativo")
        self.auto_backup.toggled.connect(lambda v: self._set("backup.auto_on_start", v))
        data.add(self.auto_backup)
        head = QHBoxLayout()
        head.addWidget(label("Backups recentes", role="muted"), 1)
        head.addWidget(button("Criar backup agora", "secondary", "database", self._backup))
        head.addWidget(button("Restaurar selecionado", "ghost", "rotate-ccw", self._restore))
        data.body.addLayout(head)
        self.backups = QListWidget()
        self.backups.setMinimumHeight(160)
        data.add(self.backups)
        col.addWidget(data)

        about = Panel("Sobre")
        about.add(label(f"Marketplace Listing Automation {__version__}", role="muted"))
        about.add(label("Ícones Lucide (ISC). Fonte Manrope (SIL OFL 1.1).", role="hint"))
        col.addWidget(about)
        col.addStretch(1)

    def refresh(self) -> None:
        values = self.ctx.settings.all()
        for widget, key in ((self.timeout, "automation.step_timeout_s"), (self.retries, "automation.max_retries")):
            widget.blockSignals(True)
            widget.setValue(int(values[key]))
            widget.blockSignals(False)
        for widget, key in ((self.shots, "automation.screenshot_on_failure"), (self.auto_backup, "backup.auto_on_start")):
            widget.blockSignals(True)
            widget.setChecked(bool(values[key]))
            widget.blockSignals(False)
        self.channel.blockSignals(True)
        self.channel.setCurrentIndex(max(0, self.channel.findData(values["browser.channel"])))
        self.channel.blockSignals(False)
        self.backups.clear()
        for path in list_backups(self.ctx.paths.backups):
            item = QListWidgetItem(f"{path.name}    {path.stat().st_size / 1024:.0f} KB")
            item.setData(256, str(path))
            self.backups.addItem(item)

    def _set(self, key: str, value) -> None:
        self.ctx.settings.set(key, value)

    def _backup(self) -> None:
        create_backup(self.ctx.db, self.ctx.paths.backups, reason="manual",
                      keep=int(self.ctx.settings.get("backup.keep")))
        self.refresh()
        show_toast(self, "Backup criado", "success")

    def _restore(self) -> None:
        item = self.backups.currentItem()
        if item is None:
            inform(self, "Escolha um backup", "Selecione na lista o backup que deseja restaurar.")
            return
        if not confirm(self, "Restaurar backup", "Os dados atuais serão substituídos pelos do backup escolhido. "
                       "Um backup de segurança do estado atual é criado antes. Continuar?", "Restaurar", danger=True):
            return
        try:
            restore_backup(self.ctx.db, Path(item.data(256)), self.ctx.paths.backups)
        except (ValueError, OSError) as exc:
            inform(self, "Não foi possível restaurar", str(exc), error=True)
            return
        if self.on_restore:
            self.on_restore()
        self.refresh()
        show_toast(self, "Backup restaurado", "success")
