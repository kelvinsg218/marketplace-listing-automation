"""Marketplaces: seller accounts, their dedicated browser profiles and the connection test.

Each account has its own persistent Edge profile under the MLA data folder (never the user's personal
browser profile). Opening the account URL does not prove a login: the connection test checks the session
on pages mapped for the marketplace, and reports "Não verificada" when that check is not mapped yet.
Login, CAPTCHA and confirmations are always done by the user in the opened window.
"""
from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QGridLayout, QHBoxLayout, QLineEdit, QListWidget, QMenu, QScrollArea,
    QVBoxLayout, QWidget,
)

from mla.automation.adapters import adapter_for
from mla.automation.browser import BrowserSessionManager
from mla.automation.connection import ConnectionTester
from mla.core.enums import ConnectionStatus, Marketplace
from mla.core.models import MarketplaceAccount
from mla.core.sites import site_for
from mla.services.accounts import AccountError
from mla.ui.pages.base import Page
from mla.ui.widgets.common import (
    Callout, Panel, StatusChip, button, clear_layout, confirm, divider, format_when, inform, label, plural,
    show_toast,
)
from mla.ui.workers import TaskRunner

log = logging.getLogger(__name__)
MARKETPLACES = (Marketplace.MERCADO_LIVRE, Marketplace.SHOPEE, Marketplace.SIMULATED)
NOTES = {
    Marketplace.MERCADO_LIVRE: "Cadastre a URL da sua loja ou do painel de vendedor. O preenchimento automático do "
                               "formulário real ainda depende da inspeção autorizada da sua conta.",
    Marketplace.SHOPEE: "Cadastre a URL da Central do Vendedor. O preenchimento automático do formulário real ainda "
                        "está em desenvolvimento.",
    Marketplace.SIMULATED: "Marketplace local para testar o fluxo completo (login, preenchimento, revisão e "
                           "publicação) sem publicar nada de verdade.",
}
URL_HINTS = {
    Marketplace.MERCADO_LIVRE: "https://www.mercadolivre.com.br/…",
    Marketplace.SHOPEE: "https://seller.shopee.com.br/…",
    Marketplace.SIMULATED: "Deixe vazio para usar o painel simulado",
}


# ---------------------------------------------------------------------------- account form
class AccountDialog(QDialog):
    def __init__(self, ctx, account: MarketplaceAccount | None = None, marketplace: Marketplace | None = None,
                 parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.account = account
        self.saved: MarketplaceAccount | None = None
        editing = account is not None
        self.setWindowTitle("Editar conta" if editing else "Adicionar conta")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(10)
        layout.addWidget(label("Editar conta" if editing else "Adicionar conta", object_name="sectionTitle"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        self.marketplace = QComboBox()
        for m in MARKETPLACES:
            self.marketplace.addItem(m.label, m)
        chosen = account.marketplace if editing else (marketplace or Marketplace.MERCADO_LIVRE)
        self.marketplace.setCurrentIndex(self.marketplace.findData(chosen))
        self.marketplace.setEnabled(not editing)
        self.name = QLineEdit(account.label if editing else "")
        self.name.setPlaceholderText("Ex.: Loja Centro, Conta principal")
        self.url = QLineEdit(account.seller_url if editing else "")
        self.internal_id = QLineEdit(account.internal_id if editing else "")
        self.internal_id.setPlaceholderText("Opcional: gerado automaticamente")
        self.active = QCheckBox("Conta ativa")
        self.active.setChecked(account.is_active if editing else True)
        self.default = QCheckBox("Conta padrão deste marketplace")
        self.default.setChecked(account.is_default if editing else False)
        for row, (caption, widget) in enumerate((("Marketplace", self.marketplace), ("Nome da conta *", self.name),
                                                 ("URL da conta de vendedor", self.url),
                                                 ("Identificador interno", self.internal_id))):
            grid.addWidget(label(caption, role="muted"), row * 2, 0)
            grid.addWidget(widget, row * 2 + 1, 0)
        layout.addLayout(grid)
        self.url_hint = label("", role="hint", wrap=True)
        layout.addWidget(self.url_hint)
        checks = QHBoxLayout()
        checks.addWidget(self.active)
        checks.addWidget(self.default)
        checks.addStretch(1)
        layout.addLayout(checks)
        if editing:
            profile = ctx.account_service.profile_dir(account)
            layout.addWidget(label(f"Perfil dedicado do navegador: {profile}", role="hint", wrap=True))
        layout.addWidget(Callout("A URL serve para abrir a conta certa. Ela não comprova que a conta está "
                                 "autenticada: use Testar conexão depois de salvar."))
        foot = QHBoxLayout()
        foot.addStretch(1)
        foot.addWidget(button("Cancelar", "ghost", None, self.reject))
        foot.addWidget(button("Salvar conta", "primary", "check", self._save))
        layout.addLayout(foot)
        self.marketplace.currentIndexChanged.connect(self._sync)
        self._sync()

    def _sync(self) -> None:
        marketplace = Marketplace(self.marketplace.currentData())
        site = site_for(marketplace)
        self.url.setPlaceholderText(URL_HINTS[marketplace])
        allowed = ", ".join(site.allowed_hosts) if site.allowed_hosts else "páginas locais do MLA"
        self.url_hint.setText(f"Somente HTTPS em {allowed} (e subdomínios). Endereços com usuário/senha, IP ou "
                              "porta são recusados.")

    def _save(self) -> None:
        account = self.account or MarketplaceAccount(marketplace=Marketplace(self.marketplace.currentData()),
                                                     label="")
        account.label = self.name.text()
        account.seller_url = self.url.text()
        account.internal_id = self.internal_id.text()
        account.is_active = self.active.isChecked()
        account.is_default = self.default.isChecked()
        try:
            self.saved = self.ctx.account_service.save(account)
        except AccountError as exc:
            inform(self, "Não foi possível salvar", str(exc), error=True)
            return
        self.accept()


# ---------------------------------------------------------------------------- connection test
class _Hooks(QObject):
    progressed = Signal(str)
    manual = Signal(str)

    def progress(self, message: str) -> None:  # worker thread
        self.progressed.emit(message)

    def manual_action(self, message: str) -> None:  # worker thread
        self.manual.emit(message)


class ConnectionDialog(QDialog):
    """Runs ConnectionTester on a worker thread; the user logs in by hand when asked, then clicks Continuar."""

    def __init__(self, ctx, account: MarketplaceAccount, parent=None, probe_listing: bool = False):
        super().__init__(parent)
        self.ctx, self.account = ctx, account
        self.setWindowTitle(f"Testar conexão: {account.label}")
        self.setMinimumSize(620, 460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(10)
        layout.addWidget(label(f"{account.marketplace.label}: {account.label}", object_name="sectionTitle"))
        layout.addWidget(Callout("O MLA abre o navegador com o perfil dedicado desta conta (separado do seu "
                                 "navegador pessoal) e verifica a sessão. Se o site pedir login ou verificação, faça "
                                 "na janela aberta e clique em Continuar. Nada é preenchido nem publicado."))
        self.steps = QListWidget()
        layout.addWidget(self.steps, 1)
        self.manual_note = Callout(warn=True)
        self.manual_note.hide()
        layout.addWidget(self.manual_note)
        result_row = QHBoxLayout()
        self.result_chip = StatusChip(text="Testando…", tone="active")
        result_row.addWidget(self.result_chip)
        self.result_text = label("", wrap=True)
        result_row.addWidget(self.result_text, 1)
        layout.addLayout(result_row)
        foot = QHBoxLayout()
        foot.addStretch(1)
        self.continue_btn = button("Continuar", "primary", "check", self._continue)
        self.continue_btn.hide()
        self.close_btn = button("Cancelar teste", "ghost", None, self._close)
        foot.addWidget(self.continue_btn)
        foot.addWidget(self.close_btn)
        layout.addLayout(foot)

        self.hooks = _Hooks(self)
        self.hooks.progressed.connect(lambda text: self.steps.addItem(text))
        self.hooks.manual.connect(self._manual)
        self.tester = ConnectionTester(ctx, self.hooks)
        self.runner = TaskRunner(self)
        self.runner.finished.connect(self._done)
        self.runner.failed.connect(lambda message: self._done(None, message))
        account_id = account.id
        if probe_listing:
            self.runner.start(lambda _report, _cancel: self.tester.probe_listing_area(account_id))
        else:
            self.runner.start(lambda _report, _cancel: self.tester.test(account_id))

    def _manual(self, message: str) -> None:
        self.manual_note.set_text(message)
        self.manual_note.show()
        self.continue_btn.show()
        self.raise_()

    def _continue(self) -> None:
        self.manual_note.hide()
        self.continue_btn.hide()
        self.tester.continue_()

    def _done(self, result, error: str = "") -> None:
        self.manual_note.hide()
        self.continue_btn.hide()
        self.close_btn.setText("Fechar")
        if result is None:
            self.result_chip.set_status(text="Falha", tone="danger")
            self.result_text.setText(error)
            return
        if hasattr(result, "status"):
            self.result_chip.set_status(result.status)
            self.result_text.setText(result.message)
        else:  # listing-area probe
            self.result_chip.set_status(text="Acessível" if result.ok else "Não acessível",
                                        tone="success" if result.ok else "warning")
            self.result_text.setText(result.message + (f"\nCaptura salva em artifacts/{result.screenshot}"
                                                       if result.screenshot else ""))

    def _close(self) -> None:
        if self.runner.running:
            self.tester.cancel()
            self.close_btn.setText("Encerrando…")
            self.close_btn.setEnabled(False)
            self.runner.finished.connect(lambda *_: self.accept())
            self.runner.failed.connect(lambda *_: self.accept())
            return
        self.accept()

    def reject(self) -> None:
        self._close()


# ---------------------------------------------------------------------------- manual login window
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
            url = self.account.seller_url or site_for(self.account.marketplace).home_url
            session.page.goto(url)
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


# ---------------------------------------------------------------------------- page
class MarketplacesPage(Page):
    key = "marketplaces"
    title = "Marketplaces"
    subtitle = "Contas de vendedor, navegadores dedicados e teste de conexão."

    def __init__(self, ctx, navigate, parent=None):
        super().__init__(ctx, navigate, parent)
        self._login_windows: list[_LoginWindow] = []
        self.header.add_action(button("Adicionar conta", "primary", "plus", lambda: self._add(None)))
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
        for marketplace in MARKETPLACES:
            self.list.addWidget(self._section(marketplace))
        self.list.addStretch(1)

    def _section(self, marketplace: Marketplace) -> Panel:
        panel = Panel(marketplace.label)
        implemented = adapter_for(marketplace).implemented
        panel.header.addWidget(StatusChip(text="Automação disponível" if implemented else "Automação em desenvolvimento",
                                          tone="success" if implemented else "warning"))
        panel.header.addWidget(button("Adicionar conta", "ghost", "plus", lambda _checked=False, m=marketplace: self._add(m)))
        panel.add(label(NOTES[marketplace], role="muted", wrap=True))
        accounts = self.ctx.account_service.list(marketplace)
        if not accounts:
            panel.add(label("Nenhuma conta cadastrada.", role="hint"))
        for index, account in enumerate(accounts):
            if index:
                panel.add(divider())
            panel.body.addLayout(self._account_row(account))
        return panel

    def _account_row(self, account: MarketplaceAccount) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        text = QVBoxLayout()
        text.setSpacing(3)
        title = QHBoxLayout()
        title.setSpacing(8)
        title.addWidget(label(account.label))
        if account.is_default:
            title.addWidget(StatusChip(text="Padrão", tone="violet"))
        if not account.is_active:
            title.addWidget(StatusChip(text="Desativada", tone="muted"))
        title.addStretch(1)
        text.addLayout(title)
        url = account.seller_url if account.marketplace is not Marketplace.SIMULATED else "Painel simulado local"
        text.addWidget(label(url or "URL da conta não cadastrada", role="hint"))
        has_profile = self.ctx.account_service.has_profile(account)
        details = []
        if account.detected_identity and account.connection_status is ConnectionStatus.CONNECTED:
            details.append(f"Conta identificada: {account.detected_identity}")
        if account.connection_checked_at:
            details.append(f"Último teste {format_when(account.connection_checked_at)}")
        details.append("Navegador dedicado já usado" if has_profile else "Navegador dedicado ainda não aberto")
        status_line = ". ".join(details)
        status_label = label(status_line, role="hint")
        status_label.setToolTip(account.connection_message)
        text.addWidget(status_label)
        row.addLayout(text, 1)
        chip = StatusChip(account.connection_status)
        chip.setToolTip(account.connection_message)
        row.addWidget(chip)
        row.addWidget(button("Testar conexão", "secondary", "plug", lambda _checked=False, a=account: self._test(a)))
        row.addWidget(button("Abrir navegador", "ghost", "log-in", lambda _checked=False, a=account: self._open_login(a),
                             "Abre o perfil dedicado desta conta para você entrar manualmente."))
        more = button("Mais", "ghost", "settings")
        menu = QMenu(self)
        menu.addAction("Editar…", lambda _checked=False, a=account: self._edit(a))
        if not account.is_default:
            menu.addAction("Tornar padrão", lambda _checked=False, a=account: self._set_default(a))
        menu.addAction("Desativar" if account.is_active else "Ativar", lambda _checked=False, a=account: self._toggle(a))
        if site_for(account.marketplace).listing_entry_mapped:
            menu.addAction("Verificar acesso à criação de anúncios",
                           lambda _checked=False, a=account: self._test(a, probe_listing=True))
        menu.addSeparator()
        menu.addAction("Excluir conta…", lambda _checked=False, a=account: self._delete(a))
        more.setMenu(menu)
        row.addWidget(more)
        return row

    # ------------------------------------------------------------------ actions
    def _add(self, marketplace: Marketplace | None) -> None:
        dialog = AccountDialog(self.ctx, marketplace=marketplace, parent=self)
        if dialog.exec():
            self.refresh()
            show_toast(self, f"Conta {dialog.saved.label} salva. Use Testar conexão para verificar o login.",
                       "success")

    def _edit(self, account: MarketplaceAccount) -> None:
        dialog = AccountDialog(self.ctx, account, parent=self)
        if dialog.exec():
            self.refresh()
            show_toast(self, "Conta atualizada", "success")

    def _set_default(self, account: MarketplaceAccount) -> None:
        self.ctx.account_service.set_default(account.id)
        self.refresh()

    def _toggle(self, account: MarketplaceAccount) -> None:
        account.is_active = not account.is_active
        try:
            self.ctx.account_service.save(account)
        except AccountError as exc:
            inform(self, "Não foi possível alterar", str(exc), error=True)
        self.refresh()

    def _delete(self, account: MarketplaceAccount) -> None:
        drafts = self.ctx.listings.count(account.marketplace, account.id)
        extra = (f" {plural(drafts, 'anúncio preparado para ela também será excluído', 'anúncios preparados para ela também serão excluídos')}."
                 if drafts else "")
        box = QDialog(self)
        box.setWindowTitle("Excluir conta")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.addWidget(label(f"Excluir a conta {account.label}?{extra}", wrap=True))
        remove_profile = QCheckBox("Apagar também o perfil do navegador desta conta (sai da conta no MLA)")
        layout.addWidget(remove_profile)
        foot = QHBoxLayout()
        foot.addStretch(1)
        foot.addWidget(button("Cancelar", "ghost", None, box.reject))
        foot.addWidget(button("Excluir", "danger", "trash-2", box.accept))
        layout.addLayout(foot)
        if not box.exec():
            return
        try:
            self.ctx.account_service.delete(account.id, remove_profile=remove_profile.isChecked())
        except AccountError as exc:
            inform(self, "Não foi possível excluir", str(exc), error=True)
            return
        self.refresh()
        show_toast(self, f"Conta {account.label} excluída")

    def _test(self, account: MarketplaceAccount, probe_listing: bool = False) -> None:
        if account.marketplace.is_real and not confirm(
                self, "Abrir a conta real", f"Abrir o navegador na conta real {account.label} do "
                f"{account.marketplace.label}? Só leitura: o MLA verifica a sessão e não preenche nem publica nada.",
                "Abrir e testar"):
            return
        ConnectionDialog(self.ctx, account, self, probe_listing).exec()
        self.refresh()

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
