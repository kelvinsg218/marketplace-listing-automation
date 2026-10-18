"""Marketplace accounts: validation, defaults, removal and dedicated browser profiles."""
from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

from mla.core.enums import ConnectionStatus, Marketplace
from mla.core.models import MarketplaceAccount
from mla.core.sites import AccountUrlError, site_for, validate_account_url
from mla.persistence.repositories import AccountRepository

log = logging.getLogger(__name__)
_INTERNAL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,39}$")


class AccountError(ValueError):
    pass


class AccountService:
    def __init__(self, repo: AccountRepository, profiles_root: Path):
        self.repo = repo
        self.profiles_root = profiles_root

    # ------------------------------------------------------------------ queries
    def list(self, marketplace: Marketplace | None = None) -> list[MarketplaceAccount]:
        return self.repo.list(marketplace)

    def get(self, account_id: int) -> MarketplaceAccount | None:
        return self.repo.get(account_id)

    def default_for(self, marketplace: Marketplace) -> MarketplaceAccount | None:
        return self.repo.default_for(marketplace)

    def profile_dir(self, account: MarketplaceAccount) -> Path:
        """Always a folder managed by MLA; a stored path outside the root is ignored."""
        if account.profile_dir:
            stored = Path(account.profile_dir).resolve()
            root = self.profiles_root.resolve()
            if root in stored.parents:
                return stored
        return self.profiles_root / f"{account.marketplace.value}-{account.id}"

    def has_profile(self, account: MarketplaceAccount) -> bool:
        folder = self.profile_dir(account)
        return folder.exists() and any(folder.iterdir())

    # ------------------------------------------------------------------ changes
    def save(self, account: MarketplaceAccount) -> MarketplaceAccount:
        account.label = account.label.strip()
        if not account.label:
            raise AccountError("Dê um nome para identificar a conta.")
        account.internal_id = account.internal_id.strip().lower()
        if account.internal_id and not _INTERNAL_ID_RE.match(account.internal_id):
            raise AccountError("O identificador interno usa só letras minúsculas, números, '-' ou '_' "
                               "(2 a 40 caracteres).")
        if account.marketplace is Marketplace.SIMULATED and not account.seller_url.strip():
            account.seller_url = site_for(Marketplace.SIMULATED).home_url
        try:
            account.seller_url = validate_account_url(account.marketplace, account.seller_url)
        except AccountUrlError as exc:
            raise AccountError(str(exc)) from exc
        account.profile_dir = ""  # profiles are always derived from the account id
        previous = self.repo.get(account.id) if account.id is not None else None
        if previous is not None and previous.marketplace is not account.marketplace:
            raise AccountError("O marketplace de uma conta não pode ser alterado; crie outra conta.")
        try:
            self.repo.save(account)
        except ValueError as exc:
            raise AccountError(str(exc)) from exc
        if previous is not None and previous.seller_url != account.seller_url:
            self.repo.record_connection(account.id, ConnectionStatus.UNKNOWN,
                                        "URL alterada; teste a conexão novamente.")
        log.info("conta salva id=%s marketplace=%s", account.id, account.marketplace)
        return self.repo.get(account.id)  # type: ignore[return-value]

    def set_default(self, account_id: int) -> None:
        self.repo.set_default(account_id)

    def delete(self, account_id: int, remove_profile: bool = False) -> None:
        account = self.repo.get(account_id)
        if account is None:
            return
        try:
            self.repo.delete(account_id)
        except ValueError as exc:
            raise AccountError(str(exc)) from exc
        if remove_profile:
            folder = self.profile_dir(account)
            if folder.exists() and self.profiles_root.resolve() in folder.resolve().parents:
                shutil.rmtree(folder, ignore_errors=True)
        log.info("conta removida id=%s (perfil removido: %s)", account_id, remove_profile)
