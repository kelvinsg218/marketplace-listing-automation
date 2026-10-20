"""Version ordering, update feed (GitHub Releases format) and the per-user installer core."""
import hashlib
import json
import sys
import threading
import zipfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from mla.config.version import VersionError, is_newer, parse_version
from mla.services.updates import UpdateCancelled, UpdateError, UpdateService

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "installer"))
import setup_core  # noqa: E402


# ------------------------------------------------------------------ versions
def test_version_ordering():
    assert is_newer("0.1.1-beta", "0.1.0-beta")
    assert is_newer("0.1.0", "0.1.0-beta")          # final after its beta
    assert is_newer("0.1.0-rc.1", "0.1.0-beta.3")
    assert is_newer("v0.2.0", "0.1.9")
    assert not is_newer("0.1.0-beta", "0.1.0-beta")
    assert parse_version("0.1.0-beta") == parse_version("0.1.0-beta.0")
    with pytest.raises(VersionError):
        parse_version("versao nova")


# ------------------------------------------------------------------ feed
@pytest.fixture
def feed(tmp_path):
    """Local server with releases.json + installer assets, same JSON shape as api.github.com."""
    root = tmp_path / "srv"
    root.mkdir()
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_QuietHandler, directory=str(root)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"

    def publish(releases):
        (root / "releases.json").write_text(json.dumps(releases), encoding="utf-8")
        return f"{base}/releases.json"

    def asset(name, content: bytes, sha: str | None = None, digest_field: bool = False):
        (root / name).write_bytes(content)
        entry = {"name": name, "browser_download_url": f"{base}/{name}", "size": len(content)}
        sha = sha or hashlib.sha256(content).hexdigest()
        if digest_field:
            entry["digest"] = f"sha256:{sha}"
            return [entry]
        (root / f"{name}.sha256").write_text(f"{sha}  {name}\n", encoding="utf-8")
        return [entry, {"name": f"{name}.sha256", "browser_download_url": f"{base}/{name}.sha256", "size": 80}]

    yield publish, asset
    server.shutdown()


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def _release(tag, assets, prerelease=True, draft=False):
    return {"tag_name": tag, "name": f"MLA {tag}", "body": f"Notas {tag}", "draft": draft,
            "prerelease": prerelease, "published_at": "2026-10-20T10:00:00Z", "html_url": "https://x", "assets": assets}


def test_check_picks_newest_installable_release(feed, tmp_path):
    publish, asset = feed
    url = publish([
        _release("v0.1.1-beta", asset("MLA-Setup-0.1.1-beta.exe", b"novo")),
        _release("v0.1.2-beta", asset("MLA-Setup-0.1.2-beta.exe", b"rascunho"), draft=True),
        _release("v0.1.0-beta", asset("MLA-Setup-0.1.0-beta.exe", b"atual")),
        _release("v0.9.0", [{"name": "outro-arquivo.zip", "browser_download_url": "x", "size": 1}], prerelease=False),
    ])
    service = UpdateService(tmp_path / "dados", current="0.1.0-beta", feed_url=url)
    result = service.check()
    assert result.available and result.latest.version == "0.1.1-beta"  # draft and asset-less ignored
    assert result.latest.notes == "Notas v0.1.1-beta"
    assert not UpdateService(tmp_path, current="0.1.1-beta", feed_url=url).check().available


def test_stable_channel_ignores_prereleases(feed, tmp_path):
    publish, asset = feed
    url = publish([_release("v0.2.0-beta", asset("MLA-Setup-0.2.0-beta.exe", b"b"))])
    assert not UpdateService(tmp_path, current="0.1.0", feed_url=url).check().available


def test_download_is_verified_then_kept(feed, tmp_path):
    publish, asset = feed
    content = b"instalador" * 50_000
    url = publish([_release("v0.1.1-beta", asset("MLA-Setup-0.1.1-beta.exe", content))])
    service = UpdateService(tmp_path / "dados", current="0.1.0-beta", feed_url=url)
    release = service.check().latest
    seen = []
    path = service.download(release, lambda done, total: seen.append((done, total)))
    assert path.read_bytes() == content and path.parent == tmp_path / "dados" / "atualizacoes"
    assert seen[-1] == (len(content), len(content))
    assert not list(path.parent.glob("*.part"))


def test_digest_field_is_used_when_present(feed, tmp_path):
    publish, asset = feed
    url = publish([_release("v0.1.1-beta", asset("MLA-Setup-0.1.1-beta.exe", b"abc", digest_field=True))])
    service = UpdateService(tmp_path, current="0.1.0-beta", feed_url=url)
    assert service.download(service.check().latest).read_bytes() == b"abc"


def test_tampered_download_is_refused_and_removed(feed, tmp_path):
    publish, asset = feed
    url = publish([_release("v0.1.1-beta", asset("MLA-Setup-0.1.1-beta.exe", b"original", sha="0" * 64))])
    service = UpdateService(tmp_path, current="0.1.0-beta", feed_url=url)
    with pytest.raises(UpdateError, match="não confere"):
        service.download(service.check().latest)
    assert not list((tmp_path / "atualizacoes").glob("MLA-Setup-*"))


def test_release_without_checksum_is_not_installable(feed, tmp_path):
    publish, _asset = feed
    url = publish([_release("v0.1.1-beta", [{"name": "MLA-Setup-0.1.1-beta.exe",
                                             "browser_download_url": "http://127.0.0.1:1/x", "size": 3}])])
    service = UpdateService(tmp_path, current="0.1.0-beta", feed_url=url)
    with pytest.raises(UpdateError, match="SHA-256"):
        service.download(service.check().latest)


def test_cancel_stops_download(feed, tmp_path):
    publish, asset = feed
    url = publish([_release("v0.1.1-beta", asset("MLA-Setup-0.1.1-beta.exe", b"x" * 2_000_000))])
    service = UpdateService(tmp_path, current="0.1.0-beta", feed_url=url)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(UpdateCancelled):
        service.download(service.check().latest, cancel=cancel)
    assert not list((tmp_path / "atualizacoes").glob("*"))


def test_unsafe_or_missing_feed_is_reported(tmp_path):
    with pytest.raises(UpdateError, match="só HTTPS"):
        UpdateService(tmp_path, feed_url="http://exemplo.com/releases").check()
    with pytest.raises(UpdateError):
        UpdateService(tmp_path, feed_url="http://127.0.0.1:1/releases").check(timeout=2)


def test_channel_file_overrides_feed(tmp_path):
    folder = tmp_path / "atualizacoes"
    folder.mkdir()
    (folder / "canal.json").write_text(json.dumps({"feed_url": "https://exemplo.com/r", "include_prereleases": False}),
                                       encoding="utf-8")
    service = UpdateService(tmp_path, current="0.1.0-beta")
    assert service.feed_url == "https://exemplo.com/r" and service.include_prereleases is False


# ------------------------------------------------------------------ installer core
def _payload(tmp_path, version_marker: str) -> Path:
    archive = tmp_path / f"payload-{version_marker}.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("MLA.exe", f"exe {version_marker}")
        zf.writestr("_internal/lib.dll", "lib")
        zf.writestr("desinstalar.ps1", "# uninstall")
    return archive


def test_install_then_update_replaces_program_and_keeps_data(tmp_path, monkeypatch):
    monkeypatch.setenv("MLA_DATA_DIR", str(tmp_path / "dados"))
    data = tmp_path / "dados" / "mla.db"
    data.parent.mkdir(parents=True)
    data.write_text("banco do usuário")
    dest = tmp_path / "Programs" / "MLA"
    exe = setup_core.install(_payload(tmp_path, "0.1.0"), dest, "0.1.0-beta", start_menu=False, registry=False)
    assert exe.read_text() == "exe 0.1.0" and (dest / "VERSAO.txt").read_text().strip() == "0.1.0-beta"
    (dest / "arquivo-antigo.txt").write_text("sobra da versão anterior")
    setup_core.install(_payload(tmp_path, "0.1.1"), dest, "0.1.1-beta", start_menu=False, registry=False)
    assert (dest / "MLA.exe").read_text() == "exe 0.1.1"
    assert not (dest / "arquivo-antigo.txt").exists()          # program folder replaced as a whole
    assert data.read_text() == "banco do usuário"              # data untouched
    assert not dest.with_name("MLA.novo").exists() and not dest.with_name("MLA.anterior").exists()


def test_broken_payload_keeps_the_installed_version(tmp_path):
    dest = tmp_path / "Programs" / "MLA"
    setup_core.install(_payload(tmp_path, "0.1.0"), dest, "0.1.0-beta", start_menu=False, registry=False)
    broken = tmp_path / "quebrado.zip"
    with zipfile.ZipFile(broken, "w") as zf:
        zf.writestr("leia-me.txt", "sem executável")
    with pytest.raises(setup_core.InstallError):
        setup_core.install(broken, dest, "0.1.1-beta", start_menu=False, registry=False)
    assert (dest / "MLA.exe").read_text() == "exe 0.1.0"
    assert (dest / "VERSAO.txt").read_text().strip() == "0.1.0-beta"


def test_payload_with_path_traversal_is_refused(tmp_path):
    evil = tmp_path / "mau.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("MLA.exe", "x")
        zf.writestr("../../fora.txt", "y")
    with pytest.raises(setup_core.InstallError):
        setup_core.install(evil, tmp_path / "Programs" / "MLA", "0.1.0-beta", start_menu=False, registry=False)
    assert not (tmp_path / "fora.txt").exists()


def test_cleanup_removes_applied_installers_only(tmp_path):
    folder = tmp_path / "atualizacoes"
    folder.mkdir()
    for name in ("MLA-Setup-0.1.0-beta.exe", "MLA-Setup-0.1.1-beta.exe", "MLA-Setup-0.1.2-beta.exe",
                 "MLA-Setup-0.1.2-beta.exe.part", "canal.json"):
        (folder / name).write_text("x")
    assert UpdateService(tmp_path, current="0.1.1-beta").cleanup() == 3
    assert sorted(p.name for p in folder.iterdir()) == ["MLA-Setup-0.1.2-beta.exe", "canal.json"]
