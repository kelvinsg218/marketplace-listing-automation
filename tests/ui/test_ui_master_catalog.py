"""UI flows of the master catalog stage (fictitious data, no real accounts)."""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from mla.core.enums import ImportStatus, ListingStatus, Marketplace, Verification
from mla.core.models import Compatibility, Product
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


@pytest.fixture
def no_dialogs(monkeypatch):
    """Confirmation boxes answer yes; information boxes are recorded instead of blocking."""
    shown = []
    for module in ("imports", "listings", "marketplaces", "compatibility", "products", "product_editor"):
        monkeypatch.setattr(f"mla.ui.pages.{module}.confirm", lambda *a, **k: True, raising=False)
        monkeypatch.setattr(f"mla.ui.pages.{module}.inform",
                            lambda _p, title, text, error=False: shown.append((title, text)), raising=False)
    return shown


def test_import_wizard_end_to_end(window, ctx, qtbot, tmp_path, no_dialogs):
    from mla.ui.pages.imports import ImportWizard
    from conftest import make_png
    base = tmp_path / "cliente"
    make_png(base / "fotos" / "UI-1.png")
    csv = base / "produtos.csv"
    csv.write_text("codigo;nome;preco_venda;saldo;marca\nUI-1;Filtro;29,90;3;Horizonte\nUI-2;Vela;15,50;8;Horizonte\n",
                   encoding="utf-8")
    wizard = ImportWizard(ctx, window, path=csv)
    qtbot.addWidget(wizard)
    qtbot.waitUntil(lambda: wizard.analysis is not None and wizard.next_btn.isEnabled(), timeout=5000)
    wizard._next()  # preview
    assert wizard.preview_table.rowCount() == 2
    wizard._next()  # mapping
    assert wizard.mapping()["codigo"] == "sku"
    assert not wizard.next_btn.isEnabled(), "probable mappings (codigo, saldo) must be confirmed"
    wizard.confirm_probable.setChecked(True)
    assert wizard.next_btn.isEnabled()
    wizard._next()  # plan on a worker thread
    qtbot.waitUntil(lambda: wizard._page == 3, timeout=10000)
    assert wizard.rows_table.rowCount() == 2 and ctx.products.count() == 0
    wizard._next()  # commit (confirmation auto-accepted)
    qtbot.waitUntil(lambda: wizard._page == 4, timeout=10000)
    assert ctx.products.count() == 2
    assert len(ctx.products.get(ctx.products.id_for_sku("UI-1")).images) == 1
    assert ctx.imports.history()[0].status is ImportStatus.COMPLETED
    window.navigate("imports")
    assert window.pages["imports"].table.rowCount() == 1


def test_prepare_edit_approve_and_queue_listing(window, ctx, qtbot, complete_product, no_dialogs):
    from mla.ui.pages.listings import ListingEditor, PrepareListingsDialog
    product = complete_product("AN-1")
    ctx.catalog.save(product)
    dialog = PrepareListingsDialog(ctx, [product.id], window, marketplace=Marketplace.SIMULATED)
    qtbot.addWidget(dialog)
    assert dialog.ok.isEnabled()
    dialog._prepare()
    marketplace, account_id, result = dialog.result_info
    assert result.created and marketplace is Marketplace.SIMULATED
    window.navigate("listings", marketplace=Marketplace.SIMULATED, account_id=account_id)
    page = window.pages["listings"]
    assert page.model.rowCount() == 1
    listing = ctx.listings.get(result.created[0])
    editor = ListingEditor(ctx, listing, window)
    qtbot.addWidget(editor)
    assert editor.title_edit.placeholderText() == product.title
    editor.title_edit.setText("Suporte articulado para monitor com pistão")
    editor.price.setText("139,90")
    editor._revalidate()
    assert editor.approve_btn.isEnabled()
    editor._save(approve=True)
    stored = ctx.listings.get(listing.id)
    assert stored.status is ListingStatus.APPROVED and stored.price_cents == 13990
    assert ctx.products.get(product.id).price_cents == 12990, "the master product is untouched"
    page.refresh()
    assert page.send_btn.isEnabled()
    page._send()
    assert ctx.listings.get(listing.id).status is ListingStatus.QUEUED


def test_listing_page_blocks_queue_for_marketplace_without_automation(window, ctx, complete_product):
    product = complete_product("AN-ML")
    ctx.catalog.save(product)
    account = ctx.accounts.default_for(Marketplace.MERCADO_LIVRE)
    created = ctx.listings.prepare([product.id], Marketplace.MERCADO_LIVRE, account.id).created
    ctx.listings.approve(created)
    window.navigate("listings", marketplace=Marketplace.MERCADO_LIVRE)
    page = window.pages["listings"]
    assert not page.send_btn.isEnabled()
    assert "ainda não está disponível" in page.integration_note.text.text()


def test_editor_master_fields_and_compatibility(window, ctx, qtbot, complete_product, no_dialogs):
    from mla.ui.pages.product_editor import ProductEditor
    product = complete_product("ED-1")
    ctx.catalog.save(product)
    ctx.compatibility.save(Compatibility(product.id, "Uno", brand="Fiat", verification=Verification.CONFIRMED))
    editor = ProductEditor(ctx, ctx.catalog.get(product.id), window)
    qtbot.addWidget(editor)
    assert editor.compat_table.rowCount() == 1
    editor.gtin.setText("7891234567895")
    editor.cost.setText("70,00")
    editor.supplier.setText("Distribuidora Sul")
    from mla.ui.pages.product_editor import _kv_add
    _kv_add(editor.specs, "Voltagem", "12 V")
    editor.compat_items.append(Compatibility(product.id, "Gol", brand="VW"))
    editor._save()
    saved = ctx.catalog.get(product.id)
    assert (saved.gtin, saved.cost_cents, saved.supplier, saved.specs) == ("7891234567895", 7000,
                                                                           "Distribuidora Sul", {"Voltagem": "12 V"})
    assert {c.model for c in ctx.compatibility.list_for_product(product.id)} == {"Uno", "Gol"}
    window.navigate("compatibility")
    assert window.pages["compatibility"].table.rowCount() == 2


def test_add_account_validates_url(window, ctx, qtbot, no_dialogs):
    from mla.ui.pages.marketplaces import AccountDialog
    dialog = AccountDialog(ctx, marketplace=Marketplace.MERCADO_LIVRE, parent=window)
    qtbot.addWidget(dialog)
    dialog.name.setText("Loja Teste")
    dialog.url.setText("https://www.mercadolivre.com.br.golpe.com/")
    dialog._save()
    assert dialog.saved is None and "Mercado Livre" in no_dialogs[-1][1]
    dialog.url.setText("www.mercadolivre.com.br/perfil/LOJA_TESTE")
    dialog._save()
    assert dialog.saved.seller_url == "https://www.mercadolivre.com.br/perfil/LOJA_TESTE"
    window.navigate("marketplaces")  # page lists the new account without opening any browser


def test_catalog_loads_incrementally(window, ctx):
    for n in range(450):
        ctx.products.insert(Product(internal_name=f"Item {n}", sku=f"INC-{n:04d}"))
    window.navigate("products")
    model = window.pages["products"].model
    assert model.total == 450 and len(model.rows) == 200
    model.fetchMore()
    model.fetchMore()
    assert len(model.rows) == 450 and not model.canFetchMore()


def test_account_buttons_receive_the_account_not_the_click_flag(window, ctx, monkeypatch):
    """Qt's clicked(bool) must not replace the bound account/marketplace (crash seen on 2026-10-13)."""
    from PySide6.QtWidgets import QPushButton
    from mla.ui.pages import marketplaces
    seen = []
    monkeypatch.setattr(marketplaces.AccountDialog, "exec",
                        lambda self: seen.append(Marketplace(self.marketplace.currentData())) or 0)
    monkeypatch.setattr(marketplaces.ConnectionDialog, "__init__",
                        lambda self, ctx_, account, parent=None, probe_listing=False: seen.append(account) or
                        marketplaces.QDialog.__init__(self))
    monkeypatch.setattr(marketplaces.ConnectionDialog, "exec", lambda self: 0)
    window.navigate("marketplaces")
    page = window.pages["marketplaces"]
    buttons = [b for b in page.findChildren(QPushButton) if b.text() in ("Adicionar conta", "Testar conexão")]
    section_add = [b for b in buttons if b.text() == "Adicionar conta" and b.property("variant") == "ghost"]
    section_add[0].click()
    assert seen[-1] is Marketplace.MERCADO_LIVRE
    simulated_test = [b for b in buttons if b.text() == "Testar conexão"][-1]
    simulated_test.click()  # simulated account: no confirmation needed
    assert getattr(seen[-1], "marketplace", None) is Marketplace.SIMULATED
