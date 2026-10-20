"""Application entry point."""
from __future__ import annotations

import logging
import sys
import traceback

from mla import APP_DISPLAY_NAME, APP_NAME, __version__
from mla.config.logging_setup import configure_logging
from mla.config.paths import AppPaths
from mla.config.workspaces import DEFAULT_SLUG, Workspace, WorkspaceError, WorkspaceRegistry

log = logging.getLogger("mla")


def _start_workspace(base) -> tuple[WorkspaceRegistry | None, Workspace]:
    """Company opened at startup: the last one used. An unreadable company list opens the main company only."""
    registry = WorkspaceRegistry(base)
    try:
        return registry, registry.last()
    except WorkspaceError:
        return None, Workspace(DEFAULT_SLUG, "Empresa principal", base)


class CompanySession:
    """The company open in this process; switching replaces window and data context (data never mixes)."""

    def __init__(self, registry: WorkspaceRegistry | None, start_executor: bool = True):
        self.registry = registry
        self.start_executor = start_executor
        self.ctx = None
        self.window = None
        self.workspace: Workspace | None = None

    def open(self, ws: Workspace, geometry=None) -> None:
        from mla.services.context import AppContext
        from mla.ui.main_window import MainWindow

        ctx = AppContext.open(ws.paths.ensure(), startup_backup=True)
        try:
            window = MainWindow(ctx, start_executor=self.start_executor, workspace=ws, registry=self.registry,
                                on_switch=self.switch if self.registry else None)
        except Exception:
            ctx.close()
            raise
        if geometry is not None:
            window.restoreGeometry(geometry)
        window.show()
        self.ctx, self.window, self.workspace = ctx, window, ws

    def switch(self, slug: str) -> bool:
        from PySide6.QtWidgets import QMessageBox

        old_ctx, old_window, old_ws = self.ctx, self.window, self.workspace
        target = self.registry.get(slug) if self.registry else None
        if target is None or old_ws is None or target.slug == old_ws.slug:
            return False
        log.info("trocando de empresa: %s -> %s", old_ws.slug, target.slug)
        old_window.switching = True
        old_window.services.executor.stop(timeout=8)
        configure_logging(target.paths.ensure().logs)
        try:
            self.open(target, old_window.saveGeometry())
        except Exception as exc:
            configure_logging(old_ws.paths.logs)
            log.exception("falha ao abrir a empresa %s", target.slug)
            old_window.switching = False
            if self.start_executor:
                old_window.services.executor.start()
            QMessageBox.critical(old_window, APP_DISPLAY_NAME, f"Não foi possível abrir a empresa {target.name}:\n"
                                 f"{exc}\n\nA empresa {old_ws.name} continua aberta.")
            return False
        try:
            self.registry.set_last(target.slug)
        except (WorkspaceError, OSError):
            log.warning("não foi possível lembrar a última empresa aberta", exc_info=True)
        old_window.close()
        old_window.deleteLater()
        old_ctx.close()
        log.info("empresa aberta: %s (dados em %s)", target.slug, target.root)
        return True


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv
    if "--self-test" in args:
        from mla.diagnostics import main as self_test
        configure_logging(AppPaths.default().ensure().logs)
        return self_test()

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QMessageBox

    registry, workspace = _start_workspace(AppPaths.default().root)
    paths = workspace.paths.ensure()
    log_file = configure_logging(paths.logs)
    log.info("iniciando %s %s (empresa %s, dados em %s)", APP_NAME, __version__, workspace.slug, paths.root)
    if registry is None:
        log.error("lista de empresas ilegível; abrindo apenas a empresa principal")

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setApplicationVersion(__version__)
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MLA.Desktop")  # stable: pinned icons survive updates
        except (AttributeError, OSError):
            pass

    from mla.ui.theme import apply_theme
    apply_theme(app)

    def excepthook(exc_type, exc, tb):
        log.critical("erro não tratado:\n%s", "".join(traceback.format_exception(exc_type, exc, tb)))
        where = session.workspace.paths.logs if session.workspace else log_file  # current company's logs
        QMessageBox.critical(None, APP_DISPLAY_NAME,
                             f"Ocorreu um erro inesperado e ele foi registrado em:\n{where}\n\n{exc}")

    sys.excepthook = excepthook

    session = CompanySession(registry)
    try:
        session.open(workspace)
    except Exception as exc:
        log.exception("falha ao abrir o banco de dados")
        QMessageBox.critical(None, APP_DISPLAY_NAME, f"Não foi possível abrir os dados do aplicativo:\n{exc}\n\n"
                             f"Detalhes em {log_file}")
        return 1
    code = app.exec()
    session.ctx.close()
    log.info("encerrado com código %s", code)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
