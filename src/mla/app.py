"""Application entry point."""
from __future__ import annotations

import logging
import sys
import traceback

from mla import APP_DISPLAY_NAME, APP_NAME, __version__
from mla.config.logging_setup import configure_logging
from mla.config.paths import AppPaths

log = logging.getLogger("mla")


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv
    if "--self-test" in args:
        from mla.diagnostics import main as self_test
        configure_logging(AppPaths.default().ensure().logs)
        return self_test()

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QMessageBox

    paths = AppPaths.default().ensure()
    log_file = configure_logging(paths.logs)
    log.info("iniciando %s %s (dados em %s)", APP_NAME, __version__, paths.root)

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setApplicationVersion(__version__)
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"MLA.{__version__}")
        except (AttributeError, OSError):
            pass

    from mla.ui.theme import apply_theme
    apply_theme(app)

    def excepthook(exc_type, exc, tb):
        log.critical("erro não tratado:\n%s", "".join(traceback.format_exception(exc_type, exc, tb)))
        QMessageBox.critical(None, APP_DISPLAY_NAME,
                             f"Ocorreu um erro inesperado e ele foi registrado em:\n{log_file}\n\n{exc}")

    sys.excepthook = excepthook

    from mla.services.context import AppContext
    from mla.ui.main_window import MainWindow
    try:
        ctx = AppContext.open(paths, startup_backup=True)
    except Exception as exc:
        log.exception("falha ao abrir o banco de dados")
        QMessageBox.critical(None, APP_DISPLAY_NAME, f"Não foi possível abrir os dados do aplicativo:\n{exc}\n\n"
                             f"Detalhes em {log_file}")
        return 1
    window = MainWindow(ctx)
    window.show()
    code = app.exec()
    ctx.close()
    log.info("encerrado com código %s", code)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
