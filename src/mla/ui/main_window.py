from __future__ import annotations

import logging
from dataclasses import dataclass

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QMainWindow, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from mla import APP_DISPLAY_NAME, __version__
from mla.automation.executor import ExecutionManager
from mla.automation.queue import QueueManager
from mla.config.paths import resource_path
from mla.persistence.migrator import migrate
from mla.services.context import AppContext
from mla.ui.execution_bridge import ExecutionBridge
from mla.ui.icons import icon
from mla.ui.pages.automations import AutomationsPage
from mla.ui.pages.dashboard import DashboardPage
from mla.ui.pages.groups import GroupsPage
from mla.ui.pages.history import HistoryPage
from mla.ui.pages.license import LicensePage
from mla.ui.pages.marketplaces import MarketplacesPage
from mla.ui.pages.products import ProductsPage
from mla.ui.pages.settings import SettingsPage
from mla.ui.theme import T
from mla.ui.widgets.common import confirm, label, show_toast

log = logging.getLogger(__name__)

NAV = [
    ("dashboard", "Dashboard", "layout-dashboard"),
    ("products", "Produtos", "package"),
    ("groups", "Grupos", "layers"),
    ("automations", "Automações", "workflow"),
    ("history", "Histórico", "history"),
    ("marketplaces", "Marketplaces", "store"),
    ("settings", "Configurações", "settings"),
    ("license", "Licença", "key-round"),
]


@dataclass
class AutomationServices:
    queue: QueueManager
    bridge: ExecutionBridge
    executor: ExecutionManager


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext, start_executor: bool = True):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(APP_DISPLAY_NAME)
        icon_path = resource_path("app.ico")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(1360, 860)
        self.setMinimumSize(1100, 700)

        queue = QueueManager(ctx.automation_repo, ctx.products, ctx.accounts)
        recovered = queue.recover_after_restart()
        bridge = ExecutionBridge(self)
        self.services = AutomationServices(queue, bridge, ExecutionManager(ctx, queue, bridge))
        bridge.reviewRequested.connect(self._on_review_anywhere)
        bridge.manualActionRequested.connect(lambda *_: self._badge())
        bridge.itemFinished.connect(lambda *_: self._badge())

        central = QWidget()
        central.setObjectName("canvas")
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        nav = self.navigate
        self.pages = {
            "dashboard": DashboardPage(ctx, nav),
            "products": ProductsPage(ctx, nav),
            "groups": GroupsPage(ctx, nav),
            "automations": AutomationsPage(ctx, nav, self.services),
            "history": HistoryPage(ctx, nav),
            "marketplaces": MarketplacesPage(ctx, nav),
            "settings": SettingsPage(ctx, nav, on_restore=self._after_restore),
            "license": LicensePage(ctx, nav, on_change=self._update_footer),
        }
        for page in self.pages.values():
            self.stack.addWidget(page)
        for index, (key, _, _) in enumerate(NAV, start=1):
            QShortcut(QKeySequence(f"Ctrl+{index}"), self, activated=lambda k=key: self.navigate(k))
        QShortcut(QKeySequence("Ctrl+N"), self, activated=lambda: self.navigate("products", new=True))
        self.navigate("dashboard")
        self._update_footer()
        if start_executor:
            self.services.executor.start()
        if recovered:
            show_toast(self, f"{recovered} execução(ões) interrompida(s) foram recuperadas; confira em Automações.",
                       "warning")

    # ------------------------------------------------------------------ sidebar
    def _build_sidebar(self) -> QWidget:
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(224)
        col = QVBoxLayout(side)
        col.setContentsMargins(0, 26, 0, 18)
        col.setSpacing(2)
        brand = QVBoxLayout()
        brand.setContentsMargins(22, 0, 16, 22)
        brand.setSpacing(0)
        brand.addWidget(label("MLA", object_name="brand"))
        brand.addWidget(label("Marketplace Listing Automation", object_name="brandSub"))
        col.addLayout(brand)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: dict[str, QPushButton] = {}
        for index, (key, text, icon_name) in enumerate(NAV):
            if key == "settings":
                col.addStretch(1)
            btn = QPushButton(f"  {text}")
            btn.setObjectName("navButton")
            btn.setCheckable(True)
            btn.setIcon(icon(icon_name, T.text_3, 18, active_color=T.violet_hi))
            btn.setIconSize(QSize(18, 18))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(f"{text} (Ctrl+{index + 1})")
            btn.clicked.connect(lambda _c=False, k=key: self.navigate(k))
            self.nav_group.addButton(btn)
            self.nav_buttons[key] = btn
            col.addWidget(btn)
        self.footer = label("", object_name="sidebarFoot", wrap=True)
        self.footer.setContentsMargins(22, 14, 16, 0)
        col.addWidget(self.footer)
        return side

    def _update_footer(self) -> None:
        status = self.ctx.license.status()
        self.footer.setText(f"{status.label}\nVersão {__version__}")

    def _badge(self) -> None:
        pending = self.ctx.dashboard.stats().awaiting_review
        self.nav_buttons["automations"].setText("  Automações" + (f"   {pending}" if pending else ""))

    # ------------------------------------------------------------------ navigation
    def navigate(self, key: str, **kwargs) -> None:
        page = self.pages[key]
        self.nav_buttons[key].setChecked(True)
        self.stack.setCurrentWidget(page)
        page.refresh()
        if kwargs:
            page.open_with(**kwargs)

    def _on_review_anywhere(self, request) -> None:
        self._badge()
        if self.stack.currentWidget() is not self.pages["automations"]:
            show_toast(self, f"Anúncio pronto para revisão: {request.item.product_name}. Abra Automações.", "warning")

    def _after_restore(self) -> None:
        migrate(self.ctx.db, self.ctx.paths.backups)
        self._update_footer()

    def closeEvent(self, event) -> None:
        executor = self.services.executor
        if executor.current_item is not None:
            if not confirm(self, "Execução em andamento", "Há um anúncio em execução. Fechar agora interrompe o "
                           "item atual, que volta para a fila na próxima abertura. Fechar mesmo assim?",
                           "Fechar", danger=True):
                event.ignore()
                return
        executor.stop(timeout=8)
        super().closeEvent(event)
