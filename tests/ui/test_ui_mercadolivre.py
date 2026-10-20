"""Mercado Livre official API in the UI (service replaced by doubles; the service itself is tested separately)."""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from mla.core.enums import Marketplace
from mla.integrations.mercadolivre import MLConnection, ValidationOutcome
from mla.ui.main_window import MainWindow
from mla.ui.theme import apply_theme


@pytest.fixture
def window(qtbot, ctx):
    apply_theme(QApplication.instance())
    win = MainWindow(ctx, start_executor=False)
    qtbot.addWidget(win)
    win.show()
    yield win
    win.services.executor.stop(timeout=1)


def _ml_listing(ctx, complete_product):
    product = complete_product("UI-ML-1")
    ctx.catalog.save(product)
    account = ctx.accounts.default_for(Marketplace.MERCADO_LIVRE)
    listing = ctx.listings.get(ctx.listings.prepare([product.id], Marketplace.MERCADO_LIVRE, account.id).created[0])
    return product, account, listing


def test_listing_editor_validates_without_publishing(window, ctx, qtbot, complete_product, monkeypatch):
    from mla.ui.pages.listings import ListingEditor
    _product, _account, listing = _ml_listing(ctx, complete_product)
    calls = []

    def validate(account_id, product, payload):
        calls.append((account_id, payload.title))
        return ValidationOutcome(False, [("error", "The attributes [PART_NUMBER] are required")],
                                 [("info", "3 foto(s) do MLA não foram enviadas")], {})

    monkeypatch.setattr(ctx.mercadolivre, "validate_listing", validate)
    monkeypatch.setattr(ctx.mercadolivre, "suggest_categories",
                        lambda title: [{"category_id": "MLB47120", "category_name": "Filtros de Óleo",
                                        "domain_name": "Filtros"}])
    editor = ListingEditor(ctx, listing, window)
    qtbot.addWidget(editor)
    tools = editor.ml_tools
    assert "não conectada" in tools.status.text()
    tools._validate()
    qtbot.waitUntil(lambda: "NÃO VÁLIDO" in tools.output.toPlainText(), timeout=5000)
    assert "PART_NUMBER" in tools.output.toPlainText() and calls
    tools._suggest()
    qtbot.waitUntil(lambda: "MLB47120" in tools.output.toPlainText(), timeout=5000)


def test_simulated_listing_has_no_ml_tools(window, ctx, qtbot, complete_product):
    from mla.ui.pages.listings import ListingEditor
    product = complete_product("UI-SIM-1")
    ctx.catalog.save(product)
    account = ctx.accounts.default_for(Marketplace.SIMULATED)
    listing = ctx.listings.get(ctx.listings.prepare([product.id], Marketplace.SIMULATED, account.id).created[0])
    editor = ListingEditor(ctx, listing, window)
    qtbot.addWidget(editor)
    assert not hasattr(editor, "ml_tools")


def test_connect_dialog_opens_authorization_and_finishes(window, ctx, qtbot, monkeypatch):
    from mla.ui.pages import ml_tools
    account = ctx.accounts.default_for(Marketplace.MERCADO_LIVRE)
    opened, informed = [], []
    monkeypatch.setattr(ml_tools.QDesktopServices, "openUrl", staticmethod(lambda url: opened.append(url.toString())))
    monkeypatch.setattr(ml_tools, "inform", lambda *a, **k: informed.append(a))
    monkeypatch.setattr(ctx.mercadolivre, "finish_connect",
                        lambda account_id, pasted: MLConnection(account_id, "123", "https://x.com/r", "99", "LOJA"))
    dialog = ml_tools.MLConnectDialog(ctx, account, window)
    qtbot.addWidget(dialog)
    dialog.client_id.setText("1234567890")
    dialog.secret.setText("segredo")
    dialog.redirect.setText("https://localhost.com/redirect")
    dialog._open()
    assert opened and opened[0].startswith("https://auth.mercadolivre.com.br/authorization?")
    assert "code_challenge_method=S256" in opened[0] and "segredo" not in opened[0]
    dialog.pasted.setText("https://localhost.com/redirect?code=TG-x&state=y")
    dialog._finish()
    qtbot.waitUntil(lambda: dialog.result_connection is not None, timeout=5000)
    assert dialog.result_connection.nickname == "LOJA"


def test_marketplaces_page_shows_api_state(window, ctx):
    window.navigate("marketplaces")
    page = window.pages["marketplaces"]
    texts = [w.text() for w in page.findChildren(type(page.header.title)) if hasattr(w, "text")]
    assert any("API oficial: não conectada" in t for t in texts)
