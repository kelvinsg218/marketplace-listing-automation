"""Server-side download of an image URL with SSRF protection.

- https only, standard port, no credentials in the URL, no redirects followed;
- every address the host resolves to must be public (no loopback, private, link-local, multicast, reserved, CGNAT);
- size cap and content check (JPEG/PNG/WEBP by magic bytes, never by extension or declared type).
"""
from __future__ import annotations

import ipaddress
import socket
import urllib.request
from urllib.parse import urlparse

MAX_BYTES = 10 * 1024 * 1024
TIMEOUT = 15


class FetchRefused(ValueError):
    pass


def check_url(url: str, resolve=socket.getaddrinfo) -> str:
    u = urlparse(url.strip())
    if u.scheme != "https" or not u.hostname:
        raise FetchRefused("Use um endereço https:// completo.")
    if u.username or u.password:
        raise FetchRefused("URLs com usuário/senha não são aceitas.")
    if u.port not in (None, 443):
        raise FetchRefused("Somente a porta padrão HTTPS é aceita.")
    try:
        infos = resolve(u.hostname, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise FetchRefused("Não foi possível resolver o endereço.") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved
                or ip.is_unspecified or ip in ipaddress.ip_network("100.64.0.0/10")):
            raise FetchRefused("Endereço interno ou reservado não é permitido.")
    return url.strip()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # noqa: D401
        raise FetchRefused("Redirecionamentos não são seguidos; use o endereço final da imagem.")


def fetch_image(url: str, sniff, opener=None) -> tuple[bytes, str]:
    url = check_url(url)
    opener = opener or urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, headers={"User-Agent": "MLA-image-import/1.0"})
    try:
        with opener.open(req, timeout=TIMEOUT) as resp:
            data = resp.read(MAX_BYTES + 1)
    except FetchRefused:
        raise
    except Exception as exc:
        raise FetchRefused(f"Falha ao baixar: {type(exc).__name__}.") from exc
    if len(data) > MAX_BYTES:
        raise FetchRefused("Imagem maior que 10 MB.")
    ctype = sniff(data)
    if ctype is None:
        raise FetchRefused("O endereço não devolveu uma imagem JPG, PNG ou WEBP.")
    return data, ctype
