from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from mla.core.enums import CatalogStatus, ItemStatus, Marketplace
from mla.ui.main_window import NAV, MainWindow
from mla.ui.theme import apply_theme


@pytest.fixture
def window(qtbot, ctx):
    apply_theme(QApplication.instance())
    win = MainWindow(ctx, start_executor=False)
    qtbot.addWidget(win)
    win.show()
    yield win
    win.services.executor.stop(timeout=1)


def test_every_page_opens(window):
    for key, _, _ in NAV:
        window.navigate(key)
        assert window.stack.currentWidget() is window.pages[key]
        assert window.nav_buttons[key].isChecked()


def test_dashboard_reflects_real_data(window, ctx, complete_product):
    window.navigate("dashboard")
    assert "0 produtos no catálogo" in window.pages["dashboard"].header.subtitle.text()
    ctx.catalog.save(complete_product("D-1"))
    window.navigate("dashboard")
    assert "1 produto no catálogo" in window.pages["dashboard"].header.subtitle.text()
    tracks = window.pages["dashboard"].rail._tracks
    ready = next(s for s in tracks[0][1] if s.key == "ready")
    assert ready.count == 1


def test_product_editor_creates_product(window, ctx, qtbot, png):
    from mla.ui.pages.product_editor import ProductEditor
    editor = ProductEditor(ctx, None, window)
    qtbot.addWidget(editor)
    editor.internal_name.setText("Luminária articulada")
    editor.sku.setText("LUM-01")
    editor.title_edit.setText("Luminária de mesa articulada LED")
    editor.category.setText("Casa")
    editor.brand.setText("Acme")
    editor.description.setPlainText("Luminária LED com braço articulado e base pesada, ideal para escritório.")
    editor.gallery.add_files([png(900, 900)])
    editor.price.setText("89,90")
    editor.stock.setValue(4)
    editor.weight.setValue(800)
    editor.length.setValue(30)
    editor.width.setValue(20)
    editor.height.setValue(15)
    editor.sections[Marketplace.SIMULATED].enabled.setChecked(True)
    editor._revalidate()
    assert editor.chip._text == CatalogStatus.READY.label
    editor._save()
    product = ctx.catalog.get(ctx.products.id_for_sku("LUM-01"))
    assert product.price_cents == 8990 and product.width_mm == 200 and len(product.images) == 1
    assert product.status is CatalogStatus.READY
    assert product.enabled_marketplaces() == [Marketplace.SIMULATED]


def test_editor_flags_title_over_marketplace_limit(window, ctx, qtbot):
    from mla.ui.pages.product_editor import ProductEditor
    editor = ProductEditor(ctx, None, window)
    qtbot.addWidget(editor)
    editor.sections[Marketplace.MERCADO_LIVRE].enabled.setChecked(True)
    editor.title_edit.setText("x" * 70)
    editor._revalidate()
    assert "70/60" in editor.title_counter.text()


def test_editor_rejects_bad_price(window, ctx, qtbot):
    from mla.ui.pages.product_editor import ProductEditor
    editor = ProductEditor(ctx, None, window)
    qtbot.addWidget(editor)
    editor.internal_name.setText("X")
    editor.sku.setText("X-1")
    editor.price.setText("1,2,3")
    editor._save()
    assert ctx.products.id_for_sku("X-1") is None
    assert editor.price.property("invalid") is True


def test_products_page_search_and_filter(window, ctx, complete_product):
    from mla.core.models import Product
    ctx.catalog.save(complete_product("F-1", title="Caneca térmica"))
    ctx.catalog.save(Product(internal_name="Rascunho", sku="F-2"))
    page = window.pages["products"]
    window.navigate("products")
    assert page.model.rowCount() == 2
    page.status_filter.setCurrentIndex(page.status_filter.findData(CatalogStatus.READY))
    assert [r.sku for r in page.model.rows] == ["F-1"]
    page.status_filter.setCurrentIndex(0)
    page.search.setText("rascunho")
    page.refresh()
    assert [r.sku for r in page.model.rows] == ["F-2"]


def test_run_from_products_enqueues_and_reports(window, ctx, complete_product, monkeypatch):
    import mla.ui.pages.automations as automations
    messages = []
    monkeypatch.setattr(automations, "inform", lambda *a, **k: messages.append(a[2]))
    product = complete_product("RUN-1")
    ctx.catalog.save(product)
    window.navigate("automations", run_products=[product.id])
    item = ctx.automation_repo.next_queued_item()
    assert item and item.product_id == product.id and item.status is ItemStatus.QUEUED
    window.navigate("automations", run_products=[product.id])  # duplicate -> reported, not queued
    assert messages and "Já está na fila" in messages[-1]


def test_review_panel_shows_form_and_routes_decision(window, ctx, complete_product, monkeypatch):
    from mla.automation.executor import Decision, ReviewRequest
    from mla.core.models import JobItem
    page = window.pages["automations"]
    window.navigate("automations")
    decisions = []
    monkeypatch.setattr(window.services.executor, "decide", lambda item_id, d: decisions.append((item_id, d)) or True)
    item = JobItem(job_id=1, product_id=1, marketplace=Marketplace.SIMULATED, account_id=3, id=42,
                   product_name="Produto X")
    page._on_review(ReviewRequest(item, {"title": "Produto X", "price": "10,00", "stock": "1", "images": "2",
                                         "category": "Outros", "description": "abc"}))
    assert page.now_stack.currentIndex() == 2
    page._decide(Decision.APPROVE)
    assert decisions == [(42, Decision.APPROVE)]
