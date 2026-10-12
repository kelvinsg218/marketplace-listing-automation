"""Turns ExecutionManager callbacks (worker thread) into Qt signals (delivered on the GUI thread)."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class ExecutionBridge(QObject):
    itemStarted = Signal(object)
    stepChanged = Signal(object, str)
    itemFinished = Signal(object, object, str)
    reviewRequested = Signal(object)
    manualActionRequested = Signal(object, str)
    logAdded = Signal(object)
    becameIdle = Signal()

    # ExecutionHooks protocol -------------------------------------------------
    def item_started(self, item) -> None:
        self.itemStarted.emit(item)

    def step_changed(self, item, step: str) -> None:
        self.stepChanged.emit(item, step)

    def item_finished(self, item, status, message: str) -> None:
        self.itemFinished.emit(item, status, message)

    def review_requested(self, request) -> None:
        self.reviewRequested.emit(request)

    def manual_action_requested(self, item, message: str) -> None:
        self.manualActionRequested.emit(item, message)

    def log_added(self, entry) -> None:
        self.logAdded.emit(entry)

    def idle(self) -> None:
        self.becameIdle.emit()
