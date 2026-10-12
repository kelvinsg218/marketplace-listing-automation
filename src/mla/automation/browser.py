"""Dedicated, persistent browser profiles per marketplace account.

Profiles live under the app data folder. The user's personal browser profile,
cookies and passwords are never read. One profile is used by one execution at a
time: an in-process lock guards this app, and Chromium's own profile lock
(SingletonLock) refuses a second app instance.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from mla.core.models import MarketplaceAccount

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext, Page, Playwright

log = logging.getLogger(__name__)


class ProfileBusyError(RuntimeError):
    pass


@dataclass
class BrowserSession:
    account: MarketplaceAccount
    context: "BrowserContext"
    page: "Page"
    profile: Path


class BrowserSessionManager:
    _locks: dict[str, threading.Lock] = {}
    _guard = threading.Lock()

    def __init__(self, profiles_root: Path, channel: str = "msedge", headless: bool = False):
        self.profiles_root = profiles_root
        self.channel = channel
        self.headless = headless
        self._playwright: "Playwright | None" = None
        self._session: BrowserSession | None = None

    def profile_dir(self, account: MarketplaceAccount) -> Path:
        if account.profile_dir:
            return Path(account.profile_dir)
        return self.profiles_root / f"{account.marketplace.value}-{account.id}"

    @classmethod
    def _lock_for(cls, profile: Path) -> threading.Lock:
        with cls._guard:
            return cls._locks.setdefault(str(profile).lower(), threading.Lock())

    @property
    def session(self) -> BrowserSession | None:
        return self._session

    def open(self, account: MarketplaceAccount) -> BrowserSession:
        """Open (or reuse) the session for an account. Must be called from the worker thread."""
        if self._session and self._session.account.id == account.id and self._alive():
            return self._session
        self.close()
        profile = self.profile_dir(account)
        profile.mkdir(parents=True, exist_ok=True)
        lock = self._lock_for(profile)
        if not lock.acquire(blocking=False):
            raise ProfileBusyError(f"O navegador da conta {account.label} já está em uso por outra execução.")
        try:
            if self._playwright is None:
                from playwright.sync_api import sync_playwright
                self._playwright = sync_playwright().start()
            kwargs = {"headless": self.headless, "no_viewport": not self.headless, "accept_downloads": False}
            if self.channel != "chromium":
                kwargs["channel"] = self.channel
            try:
                context = self._playwright.chromium.launch_persistent_context(str(profile), **kwargs)
            except Exception as exc:
                if "user data directory is already in use" in str(exc).lower() or "singleton" in str(exc).lower():
                    raise ProfileBusyError("Este perfil de navegador está aberto em outra janela. "
                                           "Feche a outra janela do navegador ou do MLA e tente de novo.") from exc
                raise
            page = context.pages[0] if context.pages else context.new_page()
        except Exception:
            lock.release()
            raise
        self._session = BrowserSession(account, context, page, profile)
        log.info("navegador aberto: %s (%s, perfil %s)", account.label, self.channel, profile.name)
        return self._session

    def _alive(self) -> bool:
        try:
            return bool(self._session and not self._session.page.is_closed())
        except Exception:
            return False

    def close(self) -> None:
        session, self._session = self._session, None
        if session is None:
            return
        try:
            session.context.close()
        except Exception as exc:
            log.warning("erro ao fechar navegador: %s", exc)
        lock = self._lock_for(session.profile)
        if lock.locked():
            lock.release()

    def shutdown(self) -> None:
        self.close()
        if self._playwright is not None:
            try:
                self._playwright.stop()
            finally:
                self._playwright = None
