"""Client companies: registry and data isolation between companies."""
import pytest

from mla.config.workspaces import COMPANIES_DIR, DEFAULT_SLUG, WorkspaceError, WorkspaceRegistry, slugify
from mla.core.models import MarketplaceAccount, Product
from mla.core.enums import Marketplace
from mla.services.context import AppContext


def test_main_company_is_the_existing_data_folder(tmp_path):
    registry = WorkspaceRegistry(tmp_path)
    main = registry.last()
    assert main.slug == DEFAULT_SLUG and main.root == tmp_path and main.is_default
    assert not (tmp_path / "workspaces.json").exists()  # nothing written until something changes


def test_create_rename_and_remember_last(tmp_path):
    registry = WorkspaceRegistry(tmp_path)
    loja = registry.create("  Auto Peças   São João ")
    assert loja.name == "Auto Peças São João" and loja.slug == "auto-pecas-sao-joao"
    assert loja.root == tmp_path / COMPANIES_DIR / "auto-pecas-sao-joao" and loja.paths.database.parent.is_dir()
    with pytest.raises(WorkspaceError, match="Já existe"):
        registry.create("auto peças são joão")
    other = registry.create("Auto-Peças São João!")  # different name, same slug -> unique folder
    assert other.slug == "auto-pecas-sao-joao-2"
    registry.set_last(loja.slug)
    assert WorkspaceRegistry(tmp_path).last().slug == loja.slug  # persisted
    assert registry.rename(loja.slug, "Peças SJ").name == "Peças SJ"
    assert [w.slug for w in registry.list()] == [DEFAULT_SLUG, "auto-pecas-sao-joao", "auto-pecas-sao-joao-2"]
    with pytest.raises(WorkspaceError):
        registry.create("   ")
    with pytest.raises(WorkspaceError):
        registry.create("x" * 61)
    with pytest.raises(WorkspaceError):
        registry.set_last("nao-existe")


def test_unreadable_registry_is_reported_not_guessed(tmp_path):
    (tmp_path / "workspaces.json").write_text("{corrompido", encoding="utf-8")
    with pytest.raises(WorkspaceError, match="lista de empresas"):
        WorkspaceRegistry(tmp_path).list()


def test_slugify_keeps_ascii_only():
    assert slugify("Loja d'Água & Cia.") == "loja-d-agua-cia"
    assert slugify("!!!") == "empresa"


def test_companies_do_not_share_catalog_accounts_or_files(tmp_path):
    registry = WorkspaceRegistry(tmp_path)
    first, second = registry.last(), registry.create("Cliente B")
    a = AppContext.open(first.paths.ensure())
    b = AppContext.open(second.paths.ensure())
    try:
        a.catalog.save(Product(internal_name="Filtro A", sku="SKU-1", price_cents=1000))
        b.catalog.save(Product(internal_name="Filtro B", sku="SKU-1", price_cents=2000))  # same SKU is fine
        assert a.products.get(a.products.id_for_sku("SKU-1")).internal_name == "Filtro A"
        assert b.products.get(b.products.id_for_sku("SKU-1")).internal_name == "Filtro B"
        a.account_service.save(MarketplaceAccount(Marketplace.SIMULATED, "Loja do cliente A"))
        assert "Loja do cliente A" not in [acc.label for acc in b.accounts.list()]
        assert a.paths.browser_profiles != b.paths.browser_profiles  # marketplace sessions stay separate
        assert not b.paths.browser_profiles.is_relative_to(a.paths.browser_profiles)
    finally:
        a.close()
        b.close()
