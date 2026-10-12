from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QInputDialog, QScrollArea, QVBoxLayout, QWidget

from mla.automation.adapters import adapter_for
from mla.automation.browser import BrowserSessionManager
from mla.core.enums import Marketplace
from mla.core.models import MarketplaceAccount
from mla.ui.pages.base import Page
from mla.ui.widgets.common import Panel, StatusChip, button, clear_layout, divider, inform, label, show_toast

log = logging.getLogger(__name__)

NOTES = {
    Marketplace.MERCADO_LIVRE: "Você já pode abrir o navegador dedicado e entrar na sua conta. O preenchimento "
                               "automático do formulário real ainda está em desenvolvimento.",
    Marketplace.SHOPEE: "Você já pode abrir o navegador dedicado e entrar na sua conta. O preenchimento "
                        "automático do formulário real ainda está em desenvolvimento.",
    Marketplace.SIMULATED: "Marketplace local para testar o fluxo completo (login, preenchimento, revisão e "
                           "publicação) sem publicar nada de verdade.",
}


class _LoginWindow(QObject):
    """Opens the account's dedicated profile so the user can log in by hand; closes when the user closes it."""
    finished = Signal(str)

    def __init__(self, ctx, account: MarketplaceAccount):
        super().__init__()
        self.ctx, self.account = ctx, account

    def start(self) -> None:
        threading.Thread(target=self._run, name="mla-login", daemon=True).start()

    def _run(self) -> None:
        manager = BrowserSessionManager(self.ctx.paths.browser_profiles, self.ctx.settings.get("browser.channel"))
        error = ""
        try:
            session = manager.open(self.account)
            session.page.goto(adapter_for(self.account.marketplace).start_url())
            closed = threading.Event()
            session.context.on("close", lambda *_: closed.set())
            while not closed.wait(0.5):
                if all(p.is_closed() for p in session.context.pages):
                    break
        except Exception as exc:
            log.warning("login manual falhou: %s", exc)
            error = str(exc).splitlines()[0]
        finally:
            manager.shutdown()
        self.finished.emit(error)


class MarketplacesPage(Page):
    key = "marketplaces"
    title = "Marketplaces"
    subtitle = "Contas conectadas e navegadores dedicados de cada uma."

    def __init__(self, ctx, navigate, parent=None):
        super().__init__(ctx, navigate, parent)
        self._login_windows: list[_LoginWindow] = []
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        self.list = QVBoxLayout(body)
        self.list.setContentsMargins(0, 0, 8, 0)
        self.list.setSpacing(16)
        scroll.setWidget(body)
        self.root.addWidget(scroll, 1)

    def refresh(self) -> None:
        clear_layout(self.list)
        for marketplace in (Marketplace.MERCADO_LIVRE, Marketplace.SHOPEE, Marketplace.SIMULATED):
            self.list.addWidget(self._section(marketplace))
        self.list.addStretch(1)

    def _section(self, marketplace: Marketplace) -> Panel:
        panel = Panel(marketplace.label)
        implemented = adapter_for(marketplace).implemented
        panel.header.addWidget(StatusChip(text="Automação disponível" if implemented else "Em desenvolvimento",
                                          tone="success" if implemented else "warning"))
        panel.header.addWidget(button("Adicionar conta", "ghost", "plus", lambda m=marketplace: self._add(m)))
        panel.add(label(NOTES[marketplace], role="muted", wrap=True))
        accounts = self.ctx.accounts.list(marketplace)
        for index, account in enumerate(accounts):
            if index:
                panel.add(divider())
            row = QHBoxLayout()
            text = QVBoxLayout()
            text.setSpacing(2)
            text.addWidget(label(account.label))
            profile = BrowserSessionManager(self.ctx.paths.browser_profiles).profile_dir(account)
            has_profile = profile.exists() and any(profile.iterdir())
            text.addWidget(label("Navegador dedicado já usado" if has_profile else "Navegador dedicado ainda não aberto",
                                 role="hint"))
            row.addLayout(text, 1)
            active = QCheckBox("Ativa")
            active.setChecked(account.is_active)
            active.toggled.connect(lambda on, a=account: self._toggle(a, on))
            row.addWidget(active)
            row.addWidget(button("Renomear", "ghost", None, lambda a=account: self._rename(a)))
            row.addWidget(button("Abrir navegador para login", "secondary", "log-in",
                                 lambda a=account: self._open_login(a)))
            panel.body.addLayout(row)
        return panel

    def _add(self, marketplace: Marketplace) -> None:
        name, ok = QInputDialog.getText(self, "Nova conta", f"Nome para identificar a conta do {marketplace.label}:")
        if ok and name.strip():
            try:
                self.ctx.accounts.save(MarketplaceAccount(marketplace=marketplace, label=name.strip()))
            except ValueError as exc:
                inform(self, "Não foi possível adicionar", str(exc), error=True)
            self.refresh()

    def _rename(self, account: MarketplaceAccount) -> None:
        name, ok = QInputDialog.getText(self, "Renomear conta", "Novo nome:", text=account.label)
        if ok and name.strip():
            account.label = name.strip()
            try:
                self.ctx.accounts.save(account)
            except ValueError as exc:
                inform(self, "Não foi possível renomear", str(exc), error=True)
            self.refresh()

    def _toggle(self, account: MarketplaceAccount, on: bool) -> None:
        account.is_active = on
        self.ctx.accounts.save(account)

    def _open_login(self, account: MarketplaceAccount) -> None:
        window = _LoginWindow(self.ctx, account)
        window.finished.connect(lambda error: self._login_closed(window, error))
        self._login_windows.append(window)
        window.start()
        show_toast(self, "Abrindo o navegador dedicado. Entre na sua conta e feche a janela quando terminar.")

    def _login_closed(self, window: _LoginWindow, error: str) -> None:
        if window in self._login_windows:
            self._login_windows.remove(window)
        if error:
            inform(self, "Não foi possível abrir o navegador", error, error=True)
        else:
            show_toast(self, "Navegador fechado. A sessão fica salva no perfil dedicado.", "success")
        self.refresh()
