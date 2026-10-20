"""Build the Windows release (development machine only).

1. PyInstaller one-folder build of the app (mla.spec) -> dist/MLA/MLA.exe
2. MLA.exe --self-test in a throwaway data folder (the developer's data is never opened)
3. Payload zip = program files + desinstalar.ps1/.cmd + LEIA-ME.txt
4. PyInstaller one-file installer (installer/setup.spec) -> dist/MLA-Setup-<versão>.exe
5. dist/MLA-Setup-<versão>.exe.sha256 (used by the in-app updater) + dist/release-notes-<versão>.md

Usage: .venv/Scripts/python tools/build_release.py [--skip-build] [--version 0.1.1-beta]
--version overrides the version for this build only (used to test updates between versions).
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
PAYLOAD = ROOT / "build" / "setup-payload"
INIT = ROOT / "src" / "mla" / "__init__.py"
EXTRA_FILES = ["desinstalar.ps1", "desinstalar.cmd", "LEIA-ME.txt"]


def current_version() -> str:
    return re.search(r'__version__ = "([^"]+)"', INIT.read_text(encoding="utf-8")).group(1)


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, cwd=ROOT, check=True)


def build_app() -> float:
    start = time.perf_counter()
    for folder in (ROOT / "build" / "mla", DIST / "MLA"):
        if folder.exists():
            shutil.rmtree(folder)
    run([sys.executable, "-m", "PyInstaller", "mla.spec", "--noconfirm"])
    return time.perf_counter() - start


def self_test(exe: Path) -> tuple[int, str]:
    with tempfile.TemporaryDirectory(prefix="mla-release-test-") as data:
        env = dict(os.environ, MLA_DATA_DIR=data)
        code = subprocess.run([str(exe), "--self-test"], env=env, timeout=300).returncode
        report = Path(data, "logs", "self-test.txt")
        text = report.read_text(encoding="utf-8") if report.exists() else "(relatório não gerado)"
    return code, text


def build_payload(version: str) -> Path:
    if PAYLOAD.exists():
        shutil.rmtree(PAYLOAD)
    PAYLOAD.mkdir(parents=True)
    archive = PAYLOAD / "MLA.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        app = DIST / "MLA"
        for path in sorted(app.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(app).as_posix())
        for name in EXTRA_FILES:
            zf.write(ROOT / "installer" / name, name)
    (PAYLOAD / "VERSAO.txt").write_text(version + "\n", encoding="utf-8")
    shutil.copy2(ROOT / "src" / "mla" / "resources" / "app.ico", PAYLOAD / "app.ico")
    return archive


def build_setup(version: str) -> Path:
    run([sys.executable, "-m", "PyInstaller", str(ROOT / "installer" / "setup.spec"), "--noconfirm",
         "--distpath", str(DIST), "--workpath", str(ROOT / "build" / "setup")])
    setup = DIST / f"MLA-Setup-{version}.exe"
    if not setup.exists():
        raise SystemExit(f"{setup} não foi gerado.")
    return setup


def main() -> int:
    version = current_version()
    if "--version" in sys.argv:
        version = sys.argv[sys.argv.index("--version") + 1]
    original = INIT.read_text(encoding="utf-8")
    try:
        if version != current_version():
            INIT.write_text(re.sub(r'__version__ = "[^"]+"', f'__version__ = "{version}"', original),
                            encoding="utf-8")
        if "--skip-build" not in sys.argv:
            print(f"Construindo MLA {version}…", flush=True)
            print(f"Programa construído em {build_app():.0f} s", flush=True)
    finally:
        INIT.write_text(original, encoding="utf-8")  # a --version build never changes the source tree
    exe = DIST / "MLA" / "MLA.exe"
    code, report = self_test(exe)
    print(report)
    if code != 0:
        print(f"Autoteste do executável falhou (código {code}); instalador não gerado.")
        return code or 1
    if f"MLA {version} " not in report:
        print("O executável não informa a versão esperada; instalador não gerado.")
        return 1
    build_payload(version)
    start = time.perf_counter()
    setup = build_setup(version)
    digest = hashlib.sha256(setup.read_bytes()).hexdigest()
    Path(str(setup) + ".sha256").write_text(f"{digest}  {setup.name}\n", encoding="utf-8")
    source = ROOT / "installer" / "release-notes" / f"{version}.md"
    body = source.read_text(encoding="utf-8") if source.exists() else f"# MLA {version}\n"
    (DIST / f"release-notes-{version}.md").write_text(
        body.rstrip() + f"\n\nInstalador: `{setup.name}` · SHA-256 `{digest}`\n", encoding="utf-8")
    print(f"Instalador construído em {time.perf_counter() - start:.0f} s")
    print(f"Instalador: {setup} ({setup.stat().st_size / 1024 ** 2:.0f} MB)")
    print(f"SHA-256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
