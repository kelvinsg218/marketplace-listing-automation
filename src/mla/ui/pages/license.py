from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLineEdit

from mla.licensing.features import PLAN_FEATURES, Feature, Plan
from mla.licensing.license import LicenseError
from mla.ui.icons import pixmap
from mla.ui.pages.base import Page
from mla.ui.theme import T
from mla.ui.widgets.common import Panel, StatusChip, button, icon_button, inform, label, show_toast


class LicensePage(Page):
    key = "license"
    title = "Licença"
    subtitle = "Plano desta instalação. Nesta versão todos os recursos estão liberados."

    def __init__(self, ctx, navigate, on_change=None, parent=None):
        super().__init__(ctx, navigate, parent)
        self.on_change = on_change
        status = Panel("Esta instalação")
        top = QHBoxLayout()
        self.plan_label = label("", object_name="sectionTitle")
        top.addWidget(self.plan_label, 1)
        self.chip = StatusChip(text="", tone="violet")
        top.addWidget(self.chip)
        status.body.addLayout(top)
        id_row = QHBoxLayout()
        self.install_id = label("", role="muted")
        self.install_id.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        id_row.addWidget(self.install_id, 1)
        id_row.addWidget(icon_button("copy", "Copiar identificador", self._copy_id))
        status.body.addLayout(id_row)
        self.key_label = label("", role="hint")
        status.add(self.key_label)
        key_row = QHBoxLayout()
        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("MLA-PROFESSIONAL-XXXX-XXXX-XXXX")
        key_row.addWidget(self.key_input, 1)
        key_row.addWidget(button("Ativar", "primary", "key-round", self._activate))
        self.deactivate_btn = button("Remover chave", "ghost", None, self._deactivate)
        key_row.addWidget(self.deactivate_btn)
        status.body.addLayout(key_row)
        self.root.addWidget(status)

        plans = Panel("Recursos por plano")
        grid = QGridLayout()
        grid.setHorizontalSpacing(28)
        grid.setVerticalSpacing(8)
        shown = [Plan.STARTER, Plan.PROFESSIONAL, Plan.BUSINESS]
        for col, plan in enumerate(shown, start=1):
            grid.addWidget(label(plan.label, object_name="sectionTitle"), 0, col, Qt.AlignmentFlag.AlignCenter)
        for row, feature in enumerate(Feature, start=1):
            grid.addWidget(label(feature.label, role="muted"), row, 0)
            for col, plan in enumerate(shown, start=1):
                mark = label("")
                if feature in PLAN_FEATURES[plan]:
                    mark.setPixmap(pixmap("check", T.violet_hi, 16))
                mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
                grid.addWidget(mark, row, col)
        grid.setColumnStretch(4, 1)
        plans.body.addLayout(grid)
        plans.add(label("Cobrança e servidor de licenças ainda não implementados; a chave de teste valida só o "
                        "formato. Nenhum recurso é bloqueado nesta versão.", role="hint", wrap=True))
        self.root.addWidget(plans)
        self.root.addStretch(1)

    def refresh(self) -> None:
        status = self.ctx.license.status()
        self.plan_label.setText(f"Plano {status.plan.label}")
        tone = {"active": "success", "trial": "violet", "expired": "warning"}[status.status]
        self.chip.set_status(text=status.label, tone=tone)
        self.install_id.setText(f"Identificador da instalação: {status.installation_id}")
        self.key_label.setText(f"Chave ativa: {status.masked_key}" if status.license_key else "Nenhuma chave ativada.")
        self.deactivate_btn.setVisible(bool(status.license_key))

    def _copy_id(self) -> None:
        QGuiApplication.clipboard().setText(self.ctx.license.status().installation_id)
        show_toast(self, "Identificador copiado")

    def _activate(self) -> None:
        try:
            status = self.ctx.license.activate(self.key_input.text())
        except LicenseError as exc:
            inform(self, "Chave não aceita", str(exc), error=True)
            return
        self.key_input.clear()
        self.refresh()
        if self.on_change:
            self.on_change()
        show_toast(self, status.label, "success")

    def _deactivate(self) -> None:
        self.ctx.license.deactivate()
        self.refresh()
        if self.on_change:
            self.on_change()
