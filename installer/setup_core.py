"""Per-user installer logic for MLA (standard library only, so it can be unit-tested).

Program: %LOCALAPPDATA%\\Programs\\MLA  ·  data: %LOCALAPPDATA%\\MLA (never touched here).
Install/update = extract the payload next to the target, then swap folders; the previous version is restored if
anything fails. Uninstall entry: HKCU "Aplicativos instalados" -> desinstalar.ps1 (keeps the data).
"""
from __future__ import annotations

import ctypes
import logging
import os
import shutil
import subprocess
import sys
import time
import zipfile
from collections.abc import Callable
from pathlib import Path

PRODUCT = "MLA"
DISPLAY_NAME = "MLA - Marketplace Listing Automation"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\MLA"
EXE_NAME = "MLA.exe"

log = logging.getLogger("mla.setup")
Progress = Callable[[int, int, str], None]


class InstallError(RuntimeError):
    pass


def default_destination() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Programs" / PRODUCT


def data_root() -> Path:
    override = os.environ.get("MLA_DATA_DIR")
    return Path(override) if override else Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / PRODUCT


def configure_log() -> Path:
    folder = data_root() / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "instalador.log"
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    return path


# ---------------------------------------------------------------- processes
def wait_for_pid(pid: int, timeout: float = 120) -> bool:
    """True when the process ended (or never existed) within the timeout."""
    if sys.platform != "win32" or pid <= 0:
        return True
    synchronize = 0x00100000
    handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, pid)
    if not handle:
        return True
    try:
        return ctypes.windll.kernel32.WaitForSingleObject(handle, int(timeout * 1000)) == 0
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def running_instances() -> int:
    """Number of MLA.exe processes of this user (by image name)."""
    if sys.platform != "win32":
        return 0
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {EXE_NAME}", "/FO", "CSV", "/NH"],
                             capture_output=True, text=True, timeout=20,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.SubprocessError):
        return 0
    return sum(1 for line in out.splitlines() if line.lower().startswith(f'"{EXE_NAME.lower()}"'))


# ---------------------------------------------------------------- registry
def installed_version() -> str | None:
    if sys.platform != "win32":
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
            return str(winreg.QueryValueEx(key, "DisplayVersion")[0])
    except OSError:
        return None


def register(dest: Path, version: str, size_kb: int) -> None:
    import winreg
    uninstall = f'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{dest / "desinstalar.ps1"}"'
    values = {
        "DisplayName": DISPLAY_NAME, "DisplayVersion": version, "Publisher": PRODUCT,
        "InstallLocation": str(dest), "DisplayIcon": str(dest / EXE_NAME), "UninstallString": uninstall,
    }
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
        for name, value in values.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        for name in ("NoModify", "NoRepair"):
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "EstimatedSize", 0, winreg.REG_DWORD, size_kb)


# ---------------------------------------------------------------- shortcuts
def _special_folder(csidl: int) -> Path:
    buffer = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buffer)
    return Path(buffer.value)


def start_menu_shortcut() -> Path:
    return _special_folder(0x0002) / f"{PRODUCT}.lnk"  # CSIDL_PROGRAMS


def desktop_shortcut() -> Path:
    return _special_folder(0x0000) / f"{PRODUCT}.lnk"  # CSIDL_DESKTOP


def create_shortcut(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    script = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:MLA_LNK); "
              "$s.TargetPath = $env:MLA_TARGET; $s.WorkingDirectory = $env:MLA_DIR; "
              "$s.Description = 'Marketplace Listing Automation'; $s.Save()")
    env = dict(os.environ, MLA_LNK=str(link), MLA_TARGET=str(target), MLA_DIR=str(target.parent))
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], env=env,
                            capture_output=True, text=True, timeout=60,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode != 0 or not link.exists():
        raise InstallError(f"Não foi possível criar o atalho {link.name}: {result.stderr.strip()[:200]}")


# ---------------------------------------------------------------- install
def install(payload: Path, dest: Path, version: str, *, start_menu: bool = True, desktop: bool = False,
            registry: bool = True, progress: Progress | None = None) -> Path:
    """Install or update. The payload zip has the program files at its root. Returns the installed exe."""
    progress = progress or (lambda *_: None)
    dest = Path(dest)
    staging = dest.with_name(dest.name + ".novo")
    previous = dest.with_name(dest.name + ".anterior")
    for leftover in (staging, previous):
        if leftover.exists():
            shutil.rmtree(leftover, ignore_errors=True)
    log.info("instalando %s em %s (atualização: %s)", version, dest, dest.exists())
    try:
        with zipfile.ZipFile(payload) as zf:
            members = [m for m in zf.infolist() if not m.is_dir()]
            total = sum(m.file_size for m in members) or 1
            done = 0
            for member in members:
                target = (staging / member.filename).resolve()
                if not target.is_relative_to(staging.resolve()):
                    raise InstallError(f"Caminho inválido no pacote: {member.filename}")
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, target.open("wb") as out:
                    shutil.copyfileobj(src, out, 1024 * 1024)
                done += member.file_size
                progress(done, total, "Copiando arquivos")
        if not (staging / EXE_NAME).exists():
            raise InstallError(f"{EXE_NAME} não está no pacote.")
        (staging / "VERSAO.txt").write_text(version + "\n", encoding="utf-8")
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    progress(1, 1, "Substituindo a versão anterior")
    swapped = False
    try:
        if dest.exists():
            _retry(lambda: dest.rename(previous))
        _retry(lambda: staging.rename(dest))
        swapped = True
    finally:
        if not swapped:
            log.error("troca de pastas falhou; restaurando a versão anterior")
            if not dest.exists() and previous.exists():
                previous.rename(dest)
            shutil.rmtree(staging, ignore_errors=True)
    shutil.rmtree(previous, ignore_errors=True)
    exe = dest / EXE_NAME
    if start_menu:
        create_shortcut(start_menu_shortcut(), exe)
    if desktop:
        create_shortcut(desktop_shortcut(), exe)
    if registry:
        size_kb = sum(p.stat().st_size for p in dest.rglob("*") if p.is_file()) // 1024
        register(dest, version, size_kb)
    log.info("versão %s instalada em %s", version, dest)
    return exe


def _retry(action: Callable[[], object], attempts: int = 20, delay: float = 0.5) -> None:
    """Folder renames fail for a moment while antivirus or Explorer hold a handle."""
    for attempt in range(attempts):
        try:
            action()
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise InstallError("Arquivos do MLA em uso. Feche o MLA (e janelas abertas na pasta do programa) "
                                   "e tente de novo.") from None
            time.sleep(delay)


def launch(exe: Path) -> None:
    flags = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP) if sys.platform == "win32" else 0
    subprocess.Popen([str(exe)], cwd=str(exe.parent), close_fds=True, creationflags=flags)
