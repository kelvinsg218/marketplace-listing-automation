"""MLA-Setup.exe: per-user installer window (built with PyInstaller --onefile, payload embedded).

Modes:
  (no arguments)        wizard: install or update, shortcuts, open MLA at the end
  --atualizar           started by the app: waits for it to close (--aguardar-pid), shows progress, reopens MLA
  --silencioso          no window (tests / support); exit code 0 = installed
Other options: --destino <pasta>, --atalho-area-de-trabalho, --sem-registro, --abrir, --pacote <zip> --versao <v>
"""
from __future__ import annotations

import argparse
import logging
import sys
import threading
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import setup_core as core  # noqa: E402

log = logging.getLogger("mla.setup")


def bundled(*parts: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base.joinpath(*parts)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="MLA-Setup")
    parser.add_argument("--atualizar", action="store_true")
    parser.add_argument("--silencioso", action="store_true")
    parser.add_argument("--abrir", action="store_true")
    parser.add_argument("--aguardar-pid", type=int, default=0)
    parser.add_argument("--destino", default="")
    parser.add_argument("--atalho-area-de-trabalho", action="store_true")
    parser.add_argument("--sem-registro", action="store_true")
    parser.add_argument("--pacote", default="")
    parser.add_argument("--versao", default="")
    return parser.parse_args(argv)


def payload_and_version(args) -> tuple[Path, str]:
    payload = Path(args.pacote) if args.pacote else bundled("payload", "MLA.zip")
    version = args.versao or bundled("payload", "VERSAO.txt").read_text(encoding="utf-8").strip()
    if not payload.exists():
        raise core.InstallError(f"Pacote do programa não encontrado: {payload}")
    return payload, version


def run_install(args, progress=None) -> Path:
    payload, version = payload_and_version(args)
    dest = Path(args.destino) if args.destino else core.default_destination()
    if args.aguardar_pid:
        log.info("aguardando o MLA (pid %s) fechar", args.aguardar_pid)
        if not core.wait_for_pid(args.aguardar_pid, 120):
            raise core.InstallError("O MLA não fechou a tempo; feche o programa e execute a atualização de novo.")
    elif core.running_instances():
        raise core.InstallError("O MLA está aberto. Feche o programa e tente de novo.")
    desktop = args.atalho_area_de_trabalho or (args.atualizar and core.desktop_shortcut().exists())
    return core.install(payload, dest, version, desktop=desktop, registry=not args.sem_registro,
                        progress=progress)


def silent(args) -> int:
    try:
        exe = run_install(args)
    except Exception as exc:
        log.error("instalação falhou: %s\n%s", exc, traceback.format_exc())
        return 1
    if args.abrir:
        core.launch(exe)
    return 0


def gui(args) -> int:
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import (
        QApplication, QCheckBox, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, QVBoxLayout, QWidget,
    )

    app = QApplication(sys.argv[:1])
    app.setStyleSheet("""
        QWidget { background: #0C0B10; color: #EDEAF3; font-family: 'Segoe UI'; font-size: 13px; }
        QLabel#title { font-size: 20px; font-weight: 700; }
        QLabel#muted { color: #A7A1B3; }
        QPushButton { background: #1E1C26; border: 1px solid #3B3747; border-radius: 6px; padding: 8px 16px; }
        QPushButton:hover { background: #282532; }
        QPushButton#primary { background: #7B5CFF; border-color: #7B5CFF; color: white; font-weight: 600; }
        QPushButton#primary:disabled { background: #2A2733; border-color: #2A2733; color: #6F6A7B; }
        QProgressBar { background: #16151C; border: 1px solid #2A2733; border-radius: 4px; height: 8px; }
        QProgressBar::chunk { background: #7B5CFF; border-radius: 4px; }
    """)
    try:
        payload, version = payload_and_version(args)
    except Exception as exc:
        QMessageBox.critical(None, "Instalador do MLA", str(exc))
        return 1
    dest = Path(args.destino) if args.destino else core.default_destination()
    installed = core.installed_version()
    window = QWidget()
    window.setWindowTitle(f"Instalar MLA {version}")
    icon = bundled("payload", "app.ico")
    if icon.exists():
        window.setWindowIcon(QIcon(str(icon)))
    window.setFixedWidth(520)
    layout = QVBoxLayout(window)
    layout.setContentsMargins(28, 24, 28, 20)
    layout.setSpacing(12)
    title = QLabel("Atualizar o MLA" if (installed or args.atualizar) else "Instalar o MLA")
    title.setObjectName("title")
    layout.addWidget(title)
    if installed and installed != version:
        what = f"Versão instalada: {installed}. Nova versão: {version}."
    elif installed:
        what = f"A versão {version} já está instalada; instalar de novo repara os arquivos do programa."
    else:
        what = f"Marketplace Listing Automation, versão {version}."
    info = QLabel(f"{what}\n\nPrograma: {dest}\nSeus dados ficam em {core.data_root()} e não são alterados.")
    info.setObjectName("muted")
    info.setWordWrap(True)
    layout.addWidget(info)
    desktop = QCheckBox("Criar atalho na área de trabalho")
    desktop.setChecked(args.atalho_area_de_trabalho or core.desktop_shortcut().exists())
    open_after = QCheckBox("Abrir o MLA ao concluir")
    open_after.setChecked(True)
    for box in (desktop, open_after):
        layout.addWidget(box)
        box.setVisible(not args.atualizar)
    bar = QProgressBar()
    bar.setTextVisible(False)
    bar.setRange(0, 1000)
    bar.setVisible(False)
    layout.addWidget(bar)
    status = QLabel("")
    status.setObjectName("muted")
    status.setWordWrap(True)
    layout.addWidget(status)
    row = QHBoxLayout()
    row.addStretch(1)
    close_btn = QPushButton("Cancelar")
    go_btn = QPushButton("Atualizar" if installed else "Instalar")
    go_btn.setObjectName("primary")
    row.addWidget(close_btn)
    row.addWidget(go_btn)
    layout.addLayout(row)

    state = {"progress": (0, 1, ""), "done": False, "error": None, "exe": None}

    def worker():
        try:
            args.atalho_area_de_trabalho = desktop.isChecked()
            state["exe"] = run_install(args, progress=lambda d, t, m: state.__setitem__("progress", (d, t, m)))
        except Exception as exc:
            log.error("instalação falhou: %s\n%s", exc, traceback.format_exc())
            state["error"] = str(exc)
        state["done"] = True

    def poll():
        done, total, message = state["progress"]
        bar.setValue(int(1000 * done / max(total, 1)))
        if message:
            status.setText(message + "…")
        if not state["done"]:
            return
        timer.stop()
        close_btn.setEnabled(True)
        if state["error"]:
            bar.setVisible(False)
            status.setText(f"Não foi possível concluir: {state['error']}\nA versão anterior (se havia) foi mantida. "
                           f"Detalhes em {core.data_root() / 'logs' / 'instalador.log'}")
            close_btn.setText("Fechar")
            go_btn.setText("Tentar de novo")
            go_btn.setEnabled(True)
            return
        status.setText(f"MLA {version} instalado. Seus dados foram preservados.")
        close_btn.setText("Concluir")
        go_btn.setVisible(False)
        if open_after.isChecked() or args.atualizar or args.abrir:
            core.launch(state["exe"])
            QTimer.singleShot(1500 if args.atualizar else 400, window.close)

    timer = QTimer(window, interval=100, timeout=poll)

    def start():
        state.update(done=False, error=None)
        go_btn.setEnabled(False)
        close_btn.setEnabled(False)
        desktop.setEnabled(False)
        bar.setVisible(True)
        status.setText("Aguardando o MLA fechar…" if args.aguardar_pid else "Preparando…")
        threading.Thread(target=worker, daemon=True).start()
        timer.start()

    go_btn.clicked.connect(lambda _checked=False: start())
    close_btn.clicked.connect(lambda _checked=False: window.close())
    window.show()
    if args.atualizar:
        QTimer.singleShot(300, start)
    app.exec()
    return 1 if state["error"] else 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    core.configure_log()
    log.info("instalador iniciado: %s", " ".join(sys.argv[1:]))
    if args.silencioso:
        return silent(args)
    return gui(args)


if __name__ == "__main__":
    raise SystemExit(main())
