# PyInstaller spec — Windows folder distribution (dist/MLA/MLA.exe).
# Build: .venv\Scripts\pyinstaller mla.spec --noconfirm
# The browser is NOT bundled: automation drives the system Microsoft Edge (channel "msedge").
from PyInstaller.utils.hooks import collect_data_files

datas = [
    ("src/mla/resources", "mla/resources"),
    ("src/mla/persistence/migrations", "mla/persistence/migrations"),
]
# Playwright ships its Node.js driver as package data; there is no contrib hook for it.
datas += collect_data_files("playwright")

excluded = [
    "tkinter", "unittest", "pydoc", "pytest", "pytestqt",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.Qt3DCore", "PySide6.QtMultimedia",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtNetwork", "PySide6.QtOpenGL", "PySide6.QtSql", "PySide6.QtTest",
]

a = Analysis(
    ["src/mla/__main__.py"],
    pathex=["src"],
    datas=datas,
    hiddenimports=["PySide6.QtSvg"],
    excludes=excluded,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MLA",
    icon="src/mla/resources/app.ico",
    console=False,
    disable_windowed_traceback=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="MLA", upx=False)
