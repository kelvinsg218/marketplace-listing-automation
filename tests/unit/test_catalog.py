import pytest

from mla.core.enums import CatalogStatus, Marketplace
from mla.core.models import Product, ProductMarketplaceData, ProductVariant
from mla.persistence.repositories import ProductQuery
from mla.services.catalog import CatalogError


def test_create_and_reload_full_product(ctx, complete_product):
    product = complete_product()
    product.variants = [ProductVariant(name="Cor: Preto", attributes={"Cor": "Preto"}, sku="SKU-1-P", stock=2),
                        ProductVariant(name="Cor: Branco", attributes={"Cor": "Branco"}, sku="SKU-1-B", stock=3)]
    product.marketplace_data[Marketplace.MERCADO_LIVRE] = ProductMarketplaceData(
        Marketplace.MERCADO_LIVRE, enabled=True, price_cents=13990, attributes={"Modelo": "X1"})
    report = ctx.catalog.save(product)
    assert not report.catalog_errors()
    loaded = ctx.catalog.get(product.id)
    assert loaded.status is CatalogStatus.READY
    assert [v.name for v in loaded.variants] == ["Cor: Preto", "Cor: Branco"]
    assert loaded.variants[0].attributes == {"Cor": "Preto"}
    assert loaded.price_for(Marketplace.MERCADO_LIVRE) == 13990
    assert loaded.price_for(Marketplace.SIMULATED) == 12990
    assert loaded.main_image is not None and loaded.main_image.is_main
    assert set(loaded.enabled_marketplaces()) == {Marketplace.SIMULATED, Marketplace.MERCADO_LIVRE}


def test_status_derivation(ctx):
    draft = Product(internal_name="Rascunho", sku="D-1")
    ctx.catalog.save(draft)
    assert ctx.catalog.get(draft.id).status is CatalogStatus.DRAFT
    partial = Product(internal_name="Parcial", sku="P-1", title="Algo", price_cents=1000)
    ctx.catalog.save(partial)
    assert ctx.catalog.get(partial.id).status is CatalogStatus.INCOMPLETE


def test_identity_is_required_and_sku_unique(ctx, complete_product):
    with pytest.raises(CatalogError):
        ctx.catalog.save(Product(internal_name="", sku="X"))
    with pytest.raises(CatalogError):
        ctx.catalog.save(Product(internal_name="Nome", sku="com espaco"))
    ctx.catalog.save(complete_product("ABC"))
    with pytest.raises(CatalogError, match="SKU"):
        ctx.catalog.save(Product(internal_name="Outro", sku="abc"))  # case-insensitive


def test_variant_sku_cannot_clash_with_product_sku(ctx, complete_product):
    ctx.catalog.save(complete_product("BASE"))
    other = complete_product("OTHER")
    other.variants = [ProductVariant(name="V", sku="BASE", stock=1)]
    with pytest.raises(Exception, match="SKU"):
        ctx.catalog.save(other)


def test_update_keeps_id_and_changes_fields(ctx, complete_product):
    product = complete_product()
    ctx.catalog.save(product)
    product.title = "Novo título"
    product.images = product.images[:0]
    ctx.catalog.save(product)
    loaded = ctx.catalog.get(product.id)
    assert loaded.title == "Novo título"
    assert loaded.status is CatalogStatus.INCOMPLETE  # no images any more


def test_duplicate_generates_unique_sku(ctx, complete_product):
    product = complete_product("CAPA")
    product.variants = [ProductVariant(name="Azul", sku="CAPA-AZ", stock=1)]
    ctx.catalog.save(product)
    first = ctx.catalog.duplicate(product.id)
    second = ctx.catalog.duplicate(product.id)
    assert first.sku == "CAPA-COPIA"
    assert second.sku == "CAPA-COPIA-2"
    assert first.variants[0].sku is None
    assert len(first.images) == 1 and first.images[0].filename == product.images[0].filename


def test_delete_cascades_and_removes_orphan_images(ctx, complete_product):
    a = complete_product("A")
    ctx.catalog.save(a)
    b = complete_product("B")
    ctx.catalog.save(b)
    shared = a.images[0].filename
    b.images.append(a.images[0])
    ctx.catalog.save(b)
    ctx.catalog.delete([a.id])
    assert ctx.images.path_for(shared).exists()  # still used by B
    ctx.catalog.delete([b.id])
    assert not any(ctx.paths.images.iterdir())
    assert ctx.db.scalar("SELECT COUNT(*) FROM product_images") == 0


def test_search_filter_and_sort(ctx, complete_product):
    for sku, title in [("Z-1", "Zebra de pelúcia"), ("A-1", "Abajur de mesa"), ("M-1", "Mesa dobrável")]:
        ctx.catalog.save(complete_product(sku, title=title))
    ctx.catalog.save(Product(internal_name="Sem nada", sku="EMPTY"))
    assert [s.sku for s in ctx.catalog.search(ProductQuery(text="mesa"))] == ["M-1", "A-1"]
    ready = ctx.catalog.search(ProductQuery(status=CatalogStatus.READY, order_by="title", descending=False))
    assert [s.sku for s in ready] == ["A-1", "M-1", "Z-1"]
    summary = ready[0]
    assert summary.image_count == 1 and summary.main_image
    assert summary.marketplaces == [Marketplace.SIMULATED]
