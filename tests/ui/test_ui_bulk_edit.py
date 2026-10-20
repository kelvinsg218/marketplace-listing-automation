"""Bulk edit dialog (preview before writing) and the product history tab."""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from mla.core.enums import Condition
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


def test_bulk_edit_dialog_previews_then_applies(window, ctx, qtbot, complete_product, monkeypatch):
    from mla.ui.pages import bulk_edit
    from mla.ui.pages.bulk_edit import BulkEditDialog
    ids = []
    for sku in ("BE-1", "BE-2"):
        product = complete_product(sku)
        ctx.catalog.save(product)
        ids.append(product.id)
    dialog = BulkEditDialog(ctx, ids, window)
    qtbot.addWidget(dialog)
    check, editor = dialog.fields["supplier"]
    assert not editor.isEnabled()
    check.setChecked(True)
    editor.setText("Distribuidora Norte")
    cond_check, cond = dialog.fields["condition"]
    cond_check.setChecked(True)
    cond.setCurrentIndex(cond.findData(Condition.USED.value))
    assert not dialog.apply_btn.isEnabled()  # nothing previewed yet
    dialog._preview()
    assert dialog.table.rowCount() == 4 and dialog.apply_btn.isEnabled()
    assert ctx.catalog.get(ids[0]).supplier == ""  # preview wrote nothing
    editor.setText("Outro valor")  # editing after the preview requires a new preview
    assert not dialog.apply_btn.isEnabled()
    dialog._preview()
    monkeypatch.setattr(bulk_edit, "confirm", lambda *a, **k: True)
    dialog._apply()
    assert dialog.changed == 2
    assert ctx.catalog.get(ids[1]).supplier == "Outro valor"
    assert ctx.catalog.get(ids[1]).condition is Condition.USED
    assert "price_cents" not in dialog.fields and "gtin" not in dialog.fields and "stock" not in dialog.fields


def test_product_editor_shows_history_tab(window, ctx, qtbot, complete_product):
    from mla.ui.pages.product_editor import ProductEditor
    product = complete_product("HT-1")
    ctx.catalog.save(product)
    product.brand = "Nova Marca"
    ctx.catalog.save(product)
    editor = ProductEditor(ctx, ctx.catalog.get(product.id), window)
    qtbot.addWidget(editor)
    titles = [editor.tabs.tabText(i) for i in range(editor.tabs.count())]
    assert titles[-1] == "Histórico"
    table = editor.tabs.widget(editor.tabs.count() - 1).findChild(type(editor.compat_table))
    cells = [table.item(0, c).text() for c in range(5)]
    assert cells[1:] == ["Marca", "Acme", "Nova Marca", "Edição manual"]
    new_editor = ProductEditor(ctx, None, window)
    qtbot.addWidget(new_editor)
    assert "Histórico" not in [new_editor.tabs.tabText(i) for i in range(new_editor.tabs.count())]
