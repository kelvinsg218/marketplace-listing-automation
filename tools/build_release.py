"""Build the Windows release package (development machine only).

1. PyInstaller one-folder build (mla.spec) -> dist/MLA/MLA.exe
2. MLA.exe --self-test in a throwaway data folder (the developer's data is never opened)
3. dist/release/MLA-<versão>/ = MLA/ + instalar/desinstalar scripts + LEIA-ME.txt + VERSAO.txt
4. dist/MLA-<versão>-windows.zip + .sha256.txt

Usage: .venv/Scripts/python tools/build_release.py [--skip-build]
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
sys.path.insert(0, str(ROOT / "src"))
from mla import __version__  # noqa: E402

INSTALLER_FILES = ["instalar.ps1", "instalar.cmd", "desinstalar.ps1", "desinstalar.cmd", "LEIA-ME.txt"]


def run_build() -> float:
    start = time.perf_counter()
    for folder in (ROOT / "build", DIST / "MLA"):
        if folder.exists():
            shutil.rmtree(folder)
    subprocess.run([sys.executable, "-m", "PyInstaller", "mla.spec", "--noconfirm"], cwd=ROOT, check=True)
    return time.perf_counter() - start


def self_test(exe: Path) -> tuple[int, str]:
    with tempfile.TemporaryDirectory(prefix="mla-release-test-") as data:
        env = dict(os.environ, MLA_DATA_DIR=data)
        code = subprocess.run([str(exe), "--self-test"], env=env, timeout=300).returncode
        report = Path(data, "logs", "self-test.txt")
        text = report.read_text(encoding="utf-8") if report.exists() else "(relatório não gerado)"
    return code, text


def folder_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def main() -> int:
    if "--skip-build" not in sys.argv:
        print(f"Construindo MLA {__version__} com PyInstaller…", flush=True)
        print(f"Build concluído em {run_build():.0f} s", flush=True)
    exe = DIST / "MLA" / "MLA.exe"
    if not exe.exists():
        print("dist/MLA/MLA.exe não existe.")
        return 1
    code, report = self_test(exe)
    print(report)
    if code != 0:
        print(f"Autoteste do executável falhou (código {code}); pacote não gerado.")
        return code
    name = f"MLA-{__version__}"
    stage = DIST / "release" / name
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    shutil.copytree(DIST / "MLA", stage / "MLA")
    for file in INSTALLER_FILES:
        shutil.copy2(ROOT / "installer" / file, stage / file)
    (stage / "VERSAO.txt").write_text(__version__ + "\n", encoding="utf-8")
    archive = DIST / f"{name}-windows.zip"
    if archive.exists():
        archive.unlink()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(stage.parent).as_posix())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (DIST / f"{name}-windows.sha256.txt").write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    print(f"Pasta do programa: {folder_size(DIST / 'MLA') / 1024 ** 2:.0f} MB")
    print(f"Pacote: {archive} ({archive.stat().st_size / 1024 ** 2:.0f} MB)")
    print(f"SHA-256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
