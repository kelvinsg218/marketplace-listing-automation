"""Switching client companies in the running app: window, data context and logs are replaced together."""
from __future__ import annotations

import logging

import pytest
from PySide6.QtWidgets import QApplication, QInputDialog

from mla.app import CompanySession
from mla.config.workspaces import WorkspaceRegistry
from mla.core.models import Product
from mla.ui.theme import apply_theme


@pytest.fixture
def session(qtbot, tmp_path):
    apply_theme(QApplication.instance())
    registry = WorkspaceRegistry(tmp_path / "MLA")
    current = CompanySession(registry, start_executor=False)
    current.open(registry.last())
    yield current
    current.window.close()
    current.ctx.close()
    root = logging.getLogger()
    for handler in list(root.handlers):  # release log files inside tmp_path
        if getattr(handler, "_mla", False):
            root.removeHandler(handler)
            handler.close()


def test_switch_company_replaces_window_and_data(session, monkeypatch):
    first_window, first_ctx = session.window, session.ctx
    first_ctx.catalog.save(Product(internal_name="Produto da empresa principal", sku="P-1"))
    assert first_window.windowTitle().endswith("Empresa principal")
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Cliente Beta", True)))
    monkeypatch.setattr("mla.ui.main_window.confirm", lambda *a, **k: True)
    first_window._new_company()  # creates and opens it (confirm patched)
    assert session.workspace.name == "Cliente Beta"
    assert session.window is not first_window and session.window.windowTitle().endswith("Cliente Beta")
    assert session.ctx.products.id_for_sku("P-1") is None  # other company's catalog is not visible
    assert session.ctx.paths.root != first_ctx.paths.root
    assert (session.ctx.paths.logs / "mla.log").exists()  # logs follow the open company
    assert session.registry.last().slug == session.workspace.slug  # reopens here next time
    session.window.navigate("products")
    assert session.window.company_btn.text() == "Cliente Beta"
    # and back: the first company's data is intact
    session.window._switch_company("principal")
    assert session.workspace.slug == "principal"
    assert session.ctx.products.id_for_sku("P-1") is not None


def test_rename_company_updates_title(session, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Minha Loja", True)))
    session.window._rename_company()
    assert session.window.windowTitle().endswith("Minha Loja")
    assert session.registry.last().name == "Minha Loja"
