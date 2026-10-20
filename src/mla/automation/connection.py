"""Account connection test and listing-area probe (read-only, no form is filled).

Runs on a worker thread; the UI follows through ConnectionHooks. Opens only the
account's validated URL and the marketplace's mapped pages, in the account's
dedicated profile. Login, CAPTCHA and confirmations are always left to the user.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from mla.automation.browser import BrowserSessionManager, ProfileBusyError
from mla.core.enums import ConnectionStatus, Marketplace
from mla.core.models import MarketplaceAccount
from mla.core.sites import (
    AccountUrlError, SiteProfile, host_allowed, safe_url, site_for, validate_account_url,
)

log = logging.getLogger(__name__)
MAX_LOGIN_ROUNDS = 3


class ConnectionHooks(Protocol):
    def progress(self, message: str) -> None: ...
    def manual_action(self, message: str) -> None: ...


class _NullHooks:
    def progress(self, message: str) -> None:
        pass

    def manual_action(self, message: str) -> None:
        pass


@dataclass
class ConnectionResult:
    account_id: int
    status: ConnectionStatus
    message: str
    identity: str = ""
    final_url: str = ""
    steps: list[str] = field(default_factory=list)


@dataclass
class ListingProbeResult:
    account_id: int
    ok: bool
    message: str
    final_url: str = ""
    screenshot: str = ""
    steps: list[str] = field(default_factory=list)


class _Cancelled(Exception):
    pass


class ConnectionTester:
    def __init__(self, ctx, hooks: ConnectionHooks | None = None, headless: bool = False,
                 login_timeout_s: float = 600.0):
        self.ctx = ctx
        self.hooks = hooks or _NullHooks()
        self.headless = headless
        self.login_timeout_s = login_timeout_s
        self._event = threading.Event()
        self._decision: str | None = None
        self.manager: BrowserSessionManager | None = None

    # ------------------------------------------------------------------ control (any thread)
    def continue_(self) -> None:
        self._decision = "continue"
        self._event.set()

    def cancel(self) -> None:
        self._decision = "cancel"
        self._event.set()

    # ------------------------------------------------------------------ public (worker thread)
    def test(self, account_id: int) -> ConnectionResult:
        account = self.ctx.accounts.get(account_id)
        if account is None:
            return ConnectionResult(account_id, ConnectionStatus.ERROR, "Conta não encontrada.")
        steps: list[str] = []
        result = self._run(account, steps)
        self.ctx.accounts.record_connection(account.id, result.status, result.message, result.identity)
        log.info("teste de conexão conta=%s status=%s %s", account.id, result.status, result.message)
        return result

    def probe_listing_area(self, account_id: int) -> ListingProbeResult:
        account = self.ctx.accounts.get(account_id)
        if account is None:
            return ListingProbeResult(account_id, False, "Conta não encontrada.")
        site = site_for(account.marketplace)
        if not site.listing_entry_mapped:
            return ListingProbeResult(account.id, False, f"O caminho até a criação de anúncios do "
                                      f"{account.marketplace.label} ainda não foi mapeado.")
        steps: list[str] = []
        connection = self._run(account, steps, keep_open=True)
        self.ctx.accounts.record_connection(account.id, connection.status, connection.message, connection.identity)
        try:
            if connection.status is not ConnectionStatus.CONNECTED:
                return ListingProbeResult(account.id, False, f"Sem sessão ativa: {connection.message}",
                                          connection.final_url, steps=steps)
            page = self.manager.session.page
            self._say(steps, "Abrindo a página inicial de criação de anúncios (nada será preenchido).")
            try:
                page.goto(site.listing_entry_url, wait_until="domcontentloaded", timeout=self._timeout_ms())
                page.wait_for_load_state("load", timeout=self._timeout_ms())
            except Exception as exc:  # navigation error
                return ListingProbeResult(account.id, False, f"Falha ao abrir a criação de anúncios: "
                                          f"{_first_line(exc)}", safe_url(page.url), steps=steps)
            shot = self._screenshot(account, page, "criacao")
            reached = any(marker in page.url for marker in site.listing_entry_markers)
            if site.is_login_url(page.url):
                return ListingProbeResult(account.id, False, "O marketplace pediu login de novo ao abrir a "
                                          "criação de anúncios.", safe_url(page.url), shot, steps)
            if not reached:
                return ListingProbeResult(account.id, False, f"A navegação terminou em outra página: {safe_url(page.url)}",
                                          safe_url(page.url), shot, steps)
            self._say(steps, f"Página de criação aberta: {page.title()}")
            return ListingProbeResult(account.id, True, "Área de criação de anúncios acessível.", safe_url(page.url), shot,
                                      steps)
        finally:
            self._close()

    # ------------------------------------------------------------------ internals
    def _timeout_ms(self) -> int:
        return int(self.ctx.settings.get("automation.step_timeout_s")) * 1000

    def _say(self, steps: list[str], message: str) -> None:
        steps.append(message)
        self.hooks.progress(message)

    def _run(self, account: MarketplaceAccount, steps: list[str], keep_open: bool = False) -> ConnectionResult:
        site = site_for(account.marketplace)
        url = account.seller_url or (site.home_url if account.marketplace is Marketplace.SIMULATED else "")
        if not url:
            return ConnectionResult(account.id, ConnectionStatus.ERROR,
                                    "Cadastre a URL da conta de vendedor antes de testar.", steps=steps)
        try:
            url = validate_account_url(account.marketplace, url)
        except AccountUrlError as exc:
            return ConnectionResult(account.id, ConnectionStatus.ERROR, f"URL recusada: {exc}", steps=steps)
        self.manager = BrowserSessionManager(self.ctx.paths.browser_profiles, self.ctx.settings.get("browser.channel"),
                                             headless=self.headless)
        keep = False
        try:
            try:
                session = self.manager.open(account)
            except ProfileBusyError as exc:
                return ConnectionResult(account.id, ConnectionStatus.ERROR, str(exc), steps=steps)
            except Exception as exc:
                return ConnectionResult(account.id, ConnectionStatus.ERROR,
                                        f"Não foi possível abrir o navegador: {_first_line(exc)}", steps=steps)
            page = session.page
            self._say(steps, f"Navegador aberto com o perfil dedicado da conta {account.label}.")
            self._say(steps, f"Abrindo {safe_url(url)}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=self._timeout_ms())
                page.wait_for_load_state("load", timeout=self._timeout_ms())
            except Exception as exc:
                return ConnectionResult(account.id, ConnectionStatus.ERROR,
                                        f"Não foi possível abrir a URL cadastrada: {_first_line(exc)}",
                                        final_url=safe_url(page.url), steps=steps)
            self._say(steps, f"Página aberta: {page.title() or safe_url(page.url)}")
            if not self._same_site(site, page.url) and not site.is_login_url(page.url):
                self._say(steps, f"Atenção: a página redirecionou para {safe_url(page.url)}")
            if not site.session_mapped:
                return ConnectionResult(
                    account.id, ConnectionStatus.UNVERIFIED,
                    f"A página abriu, mas a verificação de login do {account.marketplace.label} ainda não foi "
                    "mapeada. A URL abrir não comprova que a conta está autenticada.", final_url=safe_url(page.url),
                    steps=steps)
            result = self._check_session(account, site, page, steps)
            keep = keep_open and result.status is ConnectionStatus.CONNECTED
            return result
        finally:
            if not keep:
                self._close()

    def _check_session(self, account, site: SiteProfile, page, steps) -> ConnectionResult:
        not_logged = ConnectionStatus.EXPIRED if account.last_connected_at else ConnectionStatus.LOGIN_REQUIRED
        for round_ in range(MAX_LOGIN_ROUNDS + 1):
            self._say(steps, "Verificando se a conta está autenticada.")
            try:
                page.goto(site.auth_check_url, wait_until="domcontentloaded", timeout=self._timeout_ms())
                page.wait_for_load_state("load", timeout=self._timeout_ms())
            except Exception as exc:
                return ConnectionResult(account.id, ConnectionStatus.ERROR,
                                        f"Falha ao verificar a sessão: {_first_line(exc)}", final_url=safe_url(page.url),
                                        steps=steps)
            if not site.is_login_url(page.url):
                identity = self._identity(site, page)
                message = "Sessão ativa" + (f" como {identity}." if identity else ".")
                self._say(steps, message)
                return ConnectionResult(account.id, ConnectionStatus.CONNECTED, message, identity, safe_url(page.url), steps)
            if round_ == MAX_LOGIN_ROUNDS:
                break
            label = "A sessão expirou" if not_logged is ConnectionStatus.EXPIRED else "É preciso entrar na conta"
            self._say(steps, f"{label}. Aguardando login manual.")
            try:
                self._wait_for_user(f"{label}. Entre na conta {account.label} no navegador aberto e depois "
                                    "clique em Continuar.")
            except _Cancelled:
                return ConnectionResult(account.id, not_logged, f"{label}; login não concluído.", final_url=safe_url(page.url),
                                        steps=steps)
        return ConnectionResult(account.id, not_logged, "O login não foi concluído.", final_url=safe_url(page.url), steps=steps)

    def _wait_for_user(self, message: str) -> None:
        self._event.clear()
        self._decision = None
        self.hooks.manual_action(message)
        if not self._event.wait(self.login_timeout_s) or self._decision != "continue":
            raise _Cancelled()

    @staticmethod
    def _same_site(site: SiteProfile, url: str) -> bool:
        from urllib.parse import urlsplit
        parts = urlsplit(url)
        if site.marketplace is Marketplace.SIMULATED:
            return parts.scheme == "file"
        return parts.scheme == "https" and host_allowed(parts.hostname or "", site.allowed_hosts)

    @staticmethod
    def _identity(site: SiteProfile, page) -> str:
        if not site.identity_selector:
            return ""
        try:
            text = page.locator(site.identity_selector).first.inner_text(timeout=5_000)
        except Exception:
            return ""
        return " ".join(text.split())[:80]

    def _screenshot(self, account: MarketplaceAccount, page, label: str) -> str:
        folder = self.ctx.paths.artifacts / "connection"
        folder.mkdir(parents=True, exist_ok=True)
        name = f"{account.marketplace.value}-{account.id}-{datetime.now():%Y%m%d-%H%M%S}-{label}.png"
        try:
            page.screenshot(path=str(folder / name), timeout=10_000)
        except Exception:
            return ""
        return f"connection/{name}"

    def _close(self) -> None:
        if self.manager is not None:
            try:
                self.manager.shutdown()
            finally:
                self.manager = None


def _first_line(exc: Exception) -> str:
    return (str(exc).splitlines() or [exc.__class__.__name__])[0][:240]
