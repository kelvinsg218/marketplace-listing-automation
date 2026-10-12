"""Whole app path: Products -> Run -> executor thread -> Qt signals -> review panel -> Approve -> published."""
from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from mla.automation.executor import Decision, ExecutionManager
from mla.core.enums import ItemStatus, Marketplace
from mla.ui.main_window import MainWindow
from mla.ui.theme import apply_theme

pytestmark = pytest.mark.browser


def test_run_review_approve_publish_through_the_ui(qtbot, ctx, complete_product):
    apply_theme(QApplication.instance())
    product = complete_product("UI-LIVE", category="Acessórios")
    ctx.catalog.save(product)
    window = MainWindow(ctx, start_executor=False)
    qtbot.addWidget(window)
    services = window.services
    services.executor = ExecutionManager(ctx, services.queue, services.bridge, headless=True)

    original_manual = services.bridge.manual_action_requested

    def human_logs_in(item, message):  # runs on the worker thread, like the real browser user
        page = services.executor._browser.session.page
        if "login.html" in page.url:
            page.fill("#email", "ui@mla.local")
            page.fill("#password", "x")
            page.click("#login-submit")
            page.wait_for_url("**/sell.html*")
        original_manual(item, message)
        services.executor.decide(item.id, Decision.CONTINUE)

    services.bridge.manual_action_requested = human_logs_in
    window.show()
    services.executor.start()
    try:
        window.navigate("automations", run_products=[product.id])
        page = window.pages["automations"]
        qtbot.waitUntil(lambda: page.now_stack.currentIndex() == 2, timeout=90_000)  # review panel shown
        assert "UI-LIVE" in page.review_title.text() or product.internal_name in page.review_title.text()
        qtbot.mouseClick(page.approve_btn, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: page.now_stack.currentIndex() == 0, timeout=90_000)
        item = ctx.automation_repo.history(text="UI-LIVE")[0]
        assert item.status is ItemStatus.PUBLISHED, item.error
        assert item.external_id.startswith("SIM-")
        listing = ctx.automation_repo.get_listing(product.id, Marketplace.SIMULATED, item.account_id)
        assert listing.external_id == item.external_id
        window.navigate("history")
        assert window.pages["history"].table.rowCount() == 1
    finally:
        services.executor.stop(timeout=30)
