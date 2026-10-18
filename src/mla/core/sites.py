"""Per-marketplace site facts and account URL validation.

Only URLs on a marketplace's allow-listed hosts are ever opened automatically.
Values marked `confirmed=False` (or empty) have not been mapped against the real
site yet; code must treat an empty field as "unknown", never guess it.
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from mla.config.paths import resource_path
from mla.core.enums import Marketplace


_BARE_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:(?!\d)")


class AccountUrlError(ValueError):
    pass


@dataclass(frozen=True)
class SiteProfile:
    marketplace: Marketplace
    allowed_hosts: tuple[str, ...]           # host or any subdomain of it
    home_url: str                            # neutral start page (manual login)
    auth_check_url: str = ""                 # page that only renders for a logged-in seller ("" = unmapped)
    login_url_markers: tuple[str, ...] = ()  # substrings of a login page URL ("" = unmapped)
    identity_selector: str = ""              # element whose text names the logged-in account ("" = unmapped)
    listing_entry_url: str = ""              # first page of the listing-creation flow ("" = unmapped)
    listing_entry_markers: tuple[str, ...] = ()  # URL substrings proving we reached it
    confirmed: bool = False                  # mapped by inspecting the real, logged-in site

    @property
    def session_mapped(self) -> bool:
        return bool(self.auth_check_url and self.login_url_markers)

    @property
    def listing_entry_mapped(self) -> bool:
        return bool(self.listing_entry_url and self.listing_entry_markers)

    def is_login_url(self, url: str) -> bool:
        return any(marker in url for marker in self.login_url_markers)


def _mock_base() -> str:
    return resource_path("mock_marketplace").as_uri()


def _simulated_profile() -> SiteProfile:
    base = _mock_base()
    return SiteProfile(
        marketplace=Marketplace.SIMULATED,
        allowed_hosts=(),
        home_url=f"{base}/home.html",
        auth_check_url=f"{base}/home.html",
        login_url_markers=("/login.html",),
        identity_selector="#seller-name",
        listing_entry_url=f"{base}/sell.html",
        listing_entry_markers=("/sell.html",),
        confirmed=True,
    )


SITES: dict[Marketplace, SiteProfile] = {
    # Mercado Livre: only the host allow-list and public home are known before inspection (phase 4.1).
    Marketplace.MERCADO_LIVRE: SiteProfile(
        marketplace=Marketplace.MERCADO_LIVRE,
        allowed_hosts=("mercadolivre.com.br",),
        home_url="https://www.mercadolivre.com.br/",
    ),
    Marketplace.SHOPEE: SiteProfile(
        marketplace=Marketplace.SHOPEE,
        allowed_hosts=("shopee.com.br",),
        home_url="https://seller.shopee.com.br/",
    ),
}


def site_for(marketplace: Marketplace) -> SiteProfile:
    if marketplace is Marketplace.SIMULATED:
        return _simulated_profile()
    return SITES[marketplace]


def host_allowed(host: str, allowed: tuple[str, ...]) -> bool:
    host = host.lower().rstrip(".")
    return any(host == base or host.endswith("." + base) for base in allowed)


def url_allowed(marketplace: Marketplace, url: str) -> bool:
    try:
        validate_account_url(marketplace, url)
        return True
    except AccountUrlError:
        return False


def validate_account_url(marketplace: Marketplace, raw: str) -> str:
    """Return a normalised URL or raise AccountUrlError with a message for the user."""
    text = (raw or "").strip()
    if not text:
        raise AccountUrlError("Informe a URL da conta de vendedor.")
    if any(ch.isspace() for ch in text):
        raise AccountUrlError("A URL não pode conter espaços.")
    if marketplace is Marketplace.SIMULATED:
        return _validate_simulated(text)
    if "://" not in text:
        if _BARE_SCHEME.match(text):  # javascript:, mailto:, data: ...
            raise AccountUrlError("Use um endereço HTTPS (começando com https://).")
        text = "https://" + text
    parts = urlsplit(text)
    if parts.scheme.lower() != "https":
        raise AccountUrlError("Use um endereço HTTPS (começando com https://).")
    if parts.username or parts.password or "@" in parts.netloc:
        raise AccountUrlError("A URL não pode conter usuário ou senha.")
    host = (parts.hostname or "").lower()
    if not host:
        raise AccountUrlError("Endereço sem domínio.")
    try:
        host.encode("ascii")
    except UnicodeEncodeError as exc:
        raise AccountUrlError("Domínio com caracteres especiais não é aceito.") from exc
    try:
        ipaddress.ip_address(host)
        is_ip = True
    except ValueError:
        is_ip = False
    if is_ip:
        raise AccountUrlError("Use o domínio do marketplace, não um endereço IP.")
    try:
        port = parts.port
    except ValueError as exc:
        raise AccountUrlError("Endereço inválido.") from exc
    if port not in (None, 443):
        raise AccountUrlError("A URL não pode indicar uma porta.")
    allowed = site_for(marketplace).allowed_hosts
    if not host_allowed(host, allowed):
        raise AccountUrlError(f"O endereço precisa ser do {marketplace.label} ({', '.join(allowed)}).")
    return urlunsplit(("https", host, parts.path or "/", parts.query, ""))


def _validate_simulated(text: str) -> str:
    parts = urlsplit(text)
    if parts.scheme != "file":
        raise AccountUrlError("O marketplace simulado só aceita as páginas locais do próprio MLA.")
    try:
        from urllib.request import url2pathname
        path = Path(url2pathname(parts.path)).resolve()
        base = resource_path("mock_marketplace").resolve()
    except (OSError, ValueError) as exc:
        raise AccountUrlError("Endereço local inválido.") from exc
    if base != path and base not in path.parents:
        raise AccountUrlError("O marketplace simulado só aceita as páginas locais do próprio MLA.")
    return urlunsplit(("file", "", parts.path, parts.query, ""))
