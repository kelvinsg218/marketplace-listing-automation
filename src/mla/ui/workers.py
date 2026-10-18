"""Run a slow service call on a worker thread and report back through Qt signals.

The function receives `progress(done, total, message)` and a `threading.Event`
it must check to stop early; services raise their own Cancelled exception.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, Signal

log = logging.getLogger(__name__)


class TaskRunner(QObject):
    progress = Signal(int, int, str)  # done, total (-1 = unknown), message
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, parent: QObject | None = None, cancelled_types: tuple[type[BaseException], ...] = ()):
        super().__init__(parent)
        self.cancel_event = threading.Event()
        self._cancelled_types = cancelled_types
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, fn: Callable[..., Any], *args: Any) -> None:
        if self.running:
            raise RuntimeError("Já existe uma operação em andamento.")
        self.cancel_event.clear()

        def report(done: int, total: int | None, message: str) -> None:
            self.progress.emit(int(done), -1 if total is None else int(total), message)

        def run() -> None:
            try:
                result = fn(*args, report, self.cancel_event)
            except self._cancelled_types:
                self.cancelled.emit()
            except Exception as exc:  # surfaced to the user as a message
                log.exception("tarefa em segundo plano falhou")
                self.failed.emit(str(exc) or exc.__class__.__name__)
            else:
                self.finished.emit(result)

        self._thread = threading.Thread(target=run, name="mla-task", daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self.cancel_event.set()

    def wait(self, timeout: float = 10.0) -> None:
        if self._thread is not None:
            self._thread.join(timeout)
