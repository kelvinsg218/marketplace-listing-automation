"""Application updates from a release feed in the GitHub Releases API format.

The feed is a public list of releases (no token is ever shipped). A release is installable only when it has the
installer asset `MLA-Setup-<versão>.exe` and a SHA-256 for it (the asset `digest` field or a
`MLA-Setup-<versão>.exe.sha256` asset). The download goes to `<dados>/atualizacoes`, is checked and only then the
installer runs, after the app closes. User data lives outside the program folder, so it is never replaced.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from mla import __version__
from mla.config.version import VersionError, is_newer, parse_version

log = logging.getLogger(__name__)

# Public releases-only repository (the source code stays private). Must exist before updates work.
DEFAULT_FEED = "https://api.github.com/repos/kelvinsg218/mla-releases/releases"
SETUP_ASSET = re.compile(r"^MLA-Setup-(?P<version>[0-9A-Za-z.\-]+)\.exe$")
MAX_DOWNLOAD = 600 * 1024 * 1024
CHANNEL_FILE = "canal.json"  # optional override: {"feed_url": "...", "include_prereleases": true}


class UpdateError(RuntimeError):
    pass


class UpdateCancelled(UpdateError):
    pass


@dataclass
class ReleaseInfo:
    version: str
    title: str
    notes: str
    published_at: str
    page_url: str
    setup_name: str
    setup_url: str
    setup_size: int
    sha256: str = ""
    sha256_url: str = ""


@dataclass
class CheckResult:
    current: str
    latest: ReleaseInfo | None
    available: bool
    message: str


def _allowed(url: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme == "https":
        return True
    return parts.scheme == "http" and parts.hostname in ("127.0.0.1", "localhost")  # local test feeds only


class UpdateService:
    def __init__(self, base_dir: Path, current: str = __version__, feed_url: str | None = None,
                 include_prereleases: bool | None = None):
        self.base_dir = Path(base_dir)
        self.folder = self.base_dir / "atualizacoes"
        self.current = current
        channel = self._channel()
        self.feed_url = feed_url or os.environ.get("MLA_UPDATE_FEED") or channel.get("feed_url") or DEFAULT_FEED
        if include_prereleases is None:
            include_prereleases = channel.get("include_prereleases", "-" in current)  # betas follow betas
        self.include_prereleases = bool(include_prereleases)

    def _channel(self) -> dict:
        path = self.base_dir / "atualizacoes" / CHANNEL_FILE
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    # ------------------------------------------------------------------ network
    def _open(self, url: str, timeout: float, accept: str = "application/vnd.github+json"):
        if not _allowed(url):
            raise UpdateError(f"Endereço de atualização recusado (só HTTPS): {url}")
        request = urllib.request.Request(url, headers={"User-Agent": f"MLA-Updater/{self.current}",
                                                       "Accept": accept})
        try:
            return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310 (scheme checked above)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise UpdateError("Canal de atualizações não encontrado (ainda não publicado).") from exc
            if exc.code == 403:
                raise UpdateError("O servidor de atualizações limitou as consultas; tente mais tarde.") from exc
            raise UpdateError(f"O servidor de atualizações respondeu HTTP {exc.code}.") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise UpdateError(f"Sem conexão com o servidor de atualizações ({exc}).") from exc

    def check(self, timeout: float = 15) -> CheckResult:
        with self._open(self.feed_url, timeout) as response:
            try:
                data = json.loads(response.read(5 * 1024 * 1024).decode("utf-8"))
            except ValueError as exc:
                raise UpdateError("Resposta inválida do servidor de atualizações.") from exc
        releases = data if isinstance(data, list) else [data]
        best: ReleaseInfo | None = None
        for item in releases:
            release = self._release(item)
            if release is None:
                continue
            if best is None or parse_version(release.version) > parse_version(best.version):
                best = release
        if best is None:
            return CheckResult(self.current, None, False, "Nenhuma versão publicada no canal de atualizações.")
        if is_newer(best.version, self.current):
            return CheckResult(self.current, best, True, f"Versão {best.version} disponível.")
        return CheckResult(self.current, best, False, f"Você já está na versão mais recente ({self.current}).")

    def _release(self, item: dict) -> ReleaseInfo | None:
        if not isinstance(item, dict) or item.get("draft"):
            return None
        if item.get("prerelease") and not self.include_prereleases:
            return None
        assets = {a.get("name", ""): a for a in item.get("assets") or [] if isinstance(a, dict)}
        for name, asset in assets.items():
            match = SETUP_ASSET.match(name)
            if not match:
                continue
            version = match.group("version")
            try:
                parse_version(version)
            except VersionError:
                continue
            digest = str(asset.get("digest") or "")
            sha_asset = assets.get(name + ".sha256", {})
            return ReleaseInfo(
                version=version, title=item.get("name") or item.get("tag_name") or version,
                notes=item.get("body") or "", published_at=item.get("published_at") or "",
                page_url=item.get("html_url") or "", setup_name=name,
                setup_url=asset.get("browser_download_url") or "", setup_size=int(asset.get("size") or 0),
                sha256=digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else "",
                sha256_url=sha_asset.get("browser_download_url") or "")
        return None

    # ------------------------------------------------------------------ download
    def expected_sha256(self, release: ReleaseInfo, timeout: float = 15) -> str:
        if release.sha256:
            return release.sha256
        if not release.sha256_url:
            raise UpdateError("A versão publicada não tem código de verificação (SHA-256); instalação recusada.")
        with self._open(release.sha256_url, timeout, accept="application/octet-stream") as response:
            text = response.read(4096).decode("utf-8", "replace")
        match = re.search(r"\b[0-9a-fA-F]{64}\b", text)
        if not match:
            raise UpdateError("Código de verificação (SHA-256) ilegível; instalação recusada.")
        return match.group(0).lower()

    def download(self, release: ReleaseInfo, progress: Callable[[int, int], None] | None = None,
                 cancel: threading.Event | None = None, timeout: float = 30) -> Path:
        """Download and verify the installer. Returns the verified file; anything wrong raises UpdateError."""
        expected = self.expected_sha256(release)
        if release.setup_size > MAX_DOWNLOAD:
            raise UpdateError("Arquivo de atualização maior que o permitido.")
        self.folder.mkdir(parents=True, exist_ok=True)
        target = self.folder / release.setup_name
        partial = target.with_suffix(target.suffix + ".part")
        digest = hashlib.sha256()
        done = 0
        try:
            with self._open(release.setup_url, timeout, accept="application/octet-stream") as response, \
                    partial.open("wb") as out:
                total = int(response.headers.get("Content-Length") or release.setup_size or 0)
                while True:
                    if cancel is not None and cancel.is_set():
                        raise UpdateCancelled("Download cancelado.")
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    done += len(chunk)
                    if done > MAX_DOWNLOAD:
                        raise UpdateError("Arquivo de atualização maior que o permitido.")
                    digest.update(chunk)
                    out.write(chunk)
                    if progress:
                        progress(done, total)
            if release.setup_size and done != release.setup_size:
                raise UpdateError(f"Download incompleto ({done} de {release.setup_size} bytes).")
            if digest.hexdigest() != expected:
                raise UpdateError("O arquivo baixado não confere com o código de verificação (SHA-256); "
                                  "nada foi instalado.")
            partial.replace(target)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        log.info("atualização %s baixada e verificada: %s (%s bytes)", release.version, target, done)
        return target

    # ------------------------------------------------------------------ install
    def launch_installer(self, setup: Path, wait_pid: int | None = None) -> subprocess.Popen:
        """Start the verified installer in update mode; it waits for this app to close, then reopens it."""
        args = [str(setup), "--atualizar", "--abrir", "--aguardar-pid", str(wait_pid or os.getpid())]
        flags = 0
        if sys.platform == "win32":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        log.info("iniciando instalador de atualização: %s", setup.name)
        return subprocess.Popen(args, close_fds=True, creationflags=flags)

    def cleanup(self) -> int:
        """Remove downloaded installers already applied (version <= current) and broken partial downloads."""
        if not self.folder.exists():
            return 0
        removed = 0
        for path in self.folder.glob("MLA-Setup-*"):
            match = SETUP_ASSET.match(path.name.removesuffix(".part"))
            try:
                stale = path.suffix == ".part" or match is None or not is_newer(match.group("version"), self.current)
            except VersionError:
                stale = True
            if stale:
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    pass
        return removed
