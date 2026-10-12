from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QVBoxLayout, QWidget

from mla.services.context import AppContext
from mla.ui.widgets.common import PageHeader


class Page(QWidget):
    """A top-level section. Subclasses build their UI and implement refresh()."""

    key = ""
    title = ""
    subtitle = ""

    def __init__(self, ctx: AppContext, navigate: Callable[..., None], parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self.navigate = navigate
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(32, 28, 32, 28)
        self.root.setSpacing(20)
        self.header = PageHeader(self.title, self.subtitle)
        self.root.addWidget(self.header)

    def refresh(self) -> None:  # called each time the page becomes visible
        pass

    def open_with(self, **kwargs) -> None:  # navigation arguments (e.g. a filter)
        pass
