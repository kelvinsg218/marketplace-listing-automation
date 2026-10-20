# PyInstaller spec for MLA-Setup-<versão>.exe (one file, program payload embedded).
# Built by tools/build_release.py, which writes build/setup-payload/{MLA.zip, VERSAO.txt, app.ico} first.
import os

root = os.path.dirname(SPECPATH)  # repository root (SPECPATH = folder of this spec)
payload = os.path.join(root, "build", "setup-payload")
version = open(os.path.join(payload, "VERSAO.txt"), encoding="utf-8").read().strip()

excluded = [
    "tkinter", "unittest", "pydoc", "pytest", "playwright", "openpyxl", "pypdf", "mla",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.Qt3DCore", "PySide6.QtMultimedia",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtNetwork", "PySide6.QtOpenGL", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtSvg",
]

a = Analysis(
    [os.path.join(SPECPATH, "setup_main.py")],
    pathex=[SPECPATH],
    datas=[(os.path.join(payload, name), "payload") for name in ("MLA.zip", "VERSAO.txt", "app.ico")],
    excludes=excluded,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=f"MLA-Setup-{version}",
    icon=os.path.join(payload, "app.ico"),
    console=False,
    upx=False,
    runtime_tmpdir=None,
)
