"""Field-level change history and safe bulk edit of the master catalog."""
import pytest

from mla.core.enums import CommercialStatus, Condition, Marketplace
from mla.core.models import ProductVariant
from mla.services.catalog import BULK_EDIT, CatalogError
from tests.unit.test_imports import CSV_HEADER, run_import, write


def _labels(ctx, product_id):
    return [(c.label, c.old, c.new, c.source) for c in ctx.catalog.history(product_id)]


def test_manual_edit_records_each_changed_field(ctx, complete_product):
    product = complete_product("H-1")
    ctx.catalog.save(product)
    assert _labels(ctx, product.id) == [("Produto criado", "", "H-1", "Edição manual")]
    product.price_cents = 15990
    product.brand = "Acme Pro"
    product.specs = {"Voltagem": "220 V"}
    product.variants = [ProductVariant(name="Preto", sku="H-1-P", stock=2)]
    product.marketplace_data[Marketplace.SIMULATED].category_id = "CAT-9"
    ctx.catalog.save(product)
    history = _labels(ctx, product.id)
    assert ("Preço de venda", "R$ 129,90", "R$ 159,90", "Edição manual") in history
    assert ("Marca", "Acme", "Acme Pro", "Edição manual") in history
    assert ("Especificação: Voltagem", "", "220 V", "Edição manual") in history
    assert any(label == "Variação H-1-P" and new.startswith("Preto") for label, _, new, _ in history)
    assert ("Marketplace simulado: categoria", "", "CAT-9", "Edição manual") in history
    count = len(history)
    ctx.catalog.save(ctx.catalog.get(product.id))  # saving without changes adds nothing
    assert len(_labels(ctx, product.id)) == count


def test_import_update_is_traced_to_the_batch(ctx, tmp_path):
    path = write(tmp_path / "base.csv", CSV_HEADER + "T-1;Filtro;10,00;5;Marca A;;\n")
    _, first, _ = run_import(ctx, path)
    pid = ctx.products.id_for_sku("T-1")
    write(path, CSV_HEADER + "T-1;Filtro;12,50;5;Marca A;;\n")
    _, second, _ = run_import(ctx, path)
    history = _labels(ctx, pid)
    assert ("Preço de venda", "R$ 10,00", "R$ 12,50", f"Importação #{second.id}") in history
    assert history[-1] == ("Produto criado", "", "T-1", f"Importação #{first.id}")


def test_history_survives_product_deletion(ctx, complete_product):
    product = complete_product("H-DEL")
    ctx.catalog.save(product)
    ctx.catalog.delete([product.id])
    rows = ctx.catalog.changes.recent()
    assert rows[0].sku == "H-DEL" and rows[0].product_id is None


def test_bulk_preview_then_update_only_descriptive_fields(ctx, complete_product):
    a, b = complete_product("B-1"), complete_product("B-2", brand="Outra")
    ctx.catalog.save(a)
    ctx.catalog.save(b)
    values = {"brand": "Acme", "supplier": " Distribuidora  Sul ", "condition": Condition.USED}
    preview = ctx.catalog.bulk_preview([a.id, b.id], values)
    assert {(r.sku, r.label, r.new) for r in preview} == {
        ("B-1", "Fornecedor", "Distribuidora Sul"), ("B-1", "Condição", "Usado"),
        ("B-2", "Marca", "Acme"), ("B-2", "Fornecedor", "Distribuidora Sul"), ("B-2", "Condição", "Usado")}
    assert ctx.catalog.get(a.id).supplier == ""  # preview writes nothing
    assert ctx.catalog.bulk_update([a.id, b.id], values) == 2
    updated = ctx.catalog.get(b.id)
    assert (updated.brand, updated.supplier, updated.condition) == ("Acme", "Distribuidora Sul", Condition.USED)
    assert ("Marca", "Outra", "Acme", BULK_EDIT) in _labels(ctx, b.id)
    assert ctx.catalog.bulk_update([a.id, b.id], values) == 0  # already applied


@pytest.mark.parametrize("values", [{"price_cents": 100}, {"stock": 3}, {"gtin": "7891234567895"}, {"sku": "X"},
                                    {"brand": "   "}, {}])
def test_bulk_edit_refuses_sensitive_or_empty_fields(ctx, complete_product, values):
    product = complete_product("B-3")
    ctx.catalog.save(product)
    with pytest.raises(CatalogError):
        ctx.catalog.bulk_update([product.id], values)


def test_bulk_edit_is_all_or_nothing(ctx, complete_product, monkeypatch):
    a, b = complete_product("B-4"), complete_product("B-5")
    ctx.catalog.save(a)
    ctx.catalog.save(b)
    original_save = ctx.catalog.save

    def failing_save(product, source="Edição manual"):
        if product.sku == "B-5":
            raise CatalogError("falha simulada.")
        return original_save(product, source)

    monkeypatch.setattr(ctx.catalog, "save", failing_save)
    with pytest.raises(CatalogError, match="Nenhum produto foi alterado"):
        ctx.catalog.bulk_update([a.id, b.id], {"commercial_status": CommercialStatus.INACTIVE})
    assert ctx.catalog.get(a.id).commercial_status is CommercialStatus.ACTIVE
    assert not any(c.source == BULK_EDIT for c in ctx.catalog.history(a.id))
