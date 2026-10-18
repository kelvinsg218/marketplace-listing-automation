"""Connection test against the simulated marketplace in headless Edge (no real account involved)."""
from __future__ import annotations

import threading

import pytest

from mla.automation.connection import ConnectionTester
from mla.core.enums import ConnectionStatus, Marketplace
from mla.core.models import MarketplaceAccount

pytestmark = pytest.mark.browser


class Human:
    """Plays the user: when asked to log in, fills the simulated login form and clicks Continuar."""

    def __init__(self, login: bool = True):
        self.login = login
        self.tester: ConnectionTester | None = None
        self.steps: list[str] = []
        self.asked: list[str] = []

    def progress(self, message: str) -> None:
        self.steps.append(message)

    def manual_action(self, message: str) -> None:
        self.asked.append(message)
        threading.Thread(target=self._act, daemon=True).start()

    def _act(self) -> None:
        if not self.login:
            self.tester.cancel()
            return
        self.tester.continue_()


def _tester(ctx, human: Human) -> ConnectionTester:
    tester = ConnectionTester(ctx, human, headless=True, login_timeout_s=30)
    human.tester = tester
    return tester


def test_simulated_login_then_session_reused(ctx):
    account = ctx.accounts.default_for(Marketplace.SIMULATED)
    human = Human()
    tester = _tester(ctx, human)
    original = tester._wait_for_user

    def wait_and_login(message):
        page = tester.manager.session.page  # the login page in the account's dedicated profile
        page.fill("#email", "loja.teste@exemplo.com")
        page.fill("#password", "x")
        page.click("#login-submit")
        page.wait_for_url("**/home.html")
        original(message)

    tester._wait_for_user = wait_and_login
    result = tester.test(account.id)
    assert result.status is ConnectionStatus.CONNECTED, result.message
    assert result.identity == "loja.teste@exemplo.com" and human.asked
    stored = ctx.accounts.get(account.id)
    assert stored.connection_status is ConnectionStatus.CONNECTED and stored.last_connected_at
    again = _tester(ctx, Human()).test(account.id)  # persistent profile: no login asked the second time
    assert again.status is ConnectionStatus.CONNECTED


def test_login_not_done_is_reported(ctx):
    account = ctx.account_service.save(MarketplaceAccount(Marketplace.SIMULATED, "Sem login"))
    result = _tester(ctx, Human(login=False)).test(account.id)
    assert result.status is ConnectionStatus.LOGIN_REQUIRED
    assert ctx.accounts.get(account.id).connection_status is ConnectionStatus.LOGIN_REQUIRED


def test_listing_area_probe_fills_nothing(ctx):
    account = ctx.accounts.default_for(Marketplace.SIMULATED)
    human = Human()
    tester = _tester(ctx, human)
    original = tester._wait_for_user

    def wait_and_login(message):
        page = tester.manager.session.page
        page.fill("#email", "vendedor@exemplo.com")
        page.fill("#password", "x")
        page.click("#login-submit")
        page.wait_for_url("**/home.html")
        original(message)

    tester._wait_for_user = wait_and_login
    probe = tester.probe_listing_area(account.id)
    assert probe.ok, probe.message
    assert probe.final_url.endswith("sell.html") and probe.screenshot


def test_unmapped_real_marketplace_is_never_reported_connected(ctx):
    """Mercado Livre session checks are not mapped yet: the test must not claim a login without opening a page."""
    account = ctx.accounts.default_for(Marketplace.MERCADO_LIVRE)  # seeded by migration 0002, no URL yet
    assert account.seller_url == ""
    result = ConnectionTester(ctx, headless=True).test(account.id)
    assert result.status is ConnectionStatus.ERROR and "URL" in result.message
