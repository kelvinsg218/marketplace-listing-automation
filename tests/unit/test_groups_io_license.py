import json
from datetime import datetime, timedelta

import pytest

from mla.core.enums import Marketplace
from mla.core.models import Product, ProductGroup, ProductVariant
from mla.licensing.features import Feature, Plan
from mla.licensing.license import LicenseError, LicenseManager, PlaceholderKeyVerifier


# ------------------------------------------------------------------ groups
def test_group_membership_order_and_validation(ctx, complete_product):
    ready = [complete_product(f"G{i}") for i in range(3)]
    for p in ready:
        ctx.catalog.save(p)
    broken = Product(internal_name="Incompleto", sku="BROKEN")
    ctx.catalog.save(broken)
    group = ctx.groups.save(ProductGroup(name="Produtos 3D", marketplaces=[Marketplace.SIMULATED]))
    other = ctx.groups.save(ProductGroup(name="Campanha"))
    ctx.groups.add_products(group.id, [ready[0].id, ready[1].id, ready[2].id, broken.id, ready[0].id])
    ctx.groups.add_products(other.id, [ready[0].id])  # same product in two groups
    assert ctx.groups.get(group.id).product_ids == [ready[0].id, ready[1].id, ready[2].id, broken.id]
    ctx.groups.move(group.id, ready[2].id, -2)
    assert ctx.groups.get(group.id).product_ids[0] == ready[2].id
    ctx.groups.remove_products(group.id, [ready[1].id])
    result = ctx.groups.validate(group.id)
    assert set(result.ready) == {ready[0].id, ready[2].id}
    assert list(result.blocked) == [broken.id]
    assert ctx.groups.get(other.id).product_ids == [ready[0].id]


def test_group_requires_unique_name_and_marketplace_to_validate(ctx):
    ctx.groups.save(ProductGroup(name="Acessórios"))
    with pytest.raises(ValueError):
        ctx.groups.save(ProductGroup(name="acessórios"))
    group = ctx.groups.save(ProductGroup(name="Vazio"))
    assert not ctx.groups.validate(group.id).ok


def test_deleting_product_removes_it_from_groups(ctx, complete_product):
    p = complete_product()
    ctx.catalog.save(p)
    group = ctx.groups.save(ProductGroup(name="G", product_ids=[p.id]))
    ctx.catalog.delete([p.id])
    assert ctx.groups.get(group.id).product_ids == []


# ------------------------------------------------------------------ import / export
def test_json_roundtrip_is_lossless(ctx, complete_product, tmp_path):
    p = complete_product("J-1")
    p.variants = [ProductVariant(name="Cor: Azul", attributes={"Cor": "Azul"}, sku="J-1-AZ", stock=2)]
    ctx.catalog.save(p)
    target = tmp_path / "out.json"
    assert ctx.import_export.export_json(target) == 1
    assert json.loads(target.read_text(encoding="utf-8"))["format"] == "mla-catalog"
    ctx.catalog.delete([p.id])
    result = ctx.import_export.import_json(target)
    assert (result.created, result.errors) == (1, [])
    loaded = ctx.catalog.get(ctx.products.id_for_sku("J-1"))
    assert loaded.variants[0].attributes == {"Cor": "Azul"}
    assert loaded.price_cents == 12990 and loaded.length_mm == 400
    assert len(loaded.images) == 1


def test_csv_roundtrip_with_excel_conventions(ctx, complete_product, tmp_path):
    ctx.catalog.save(complete_product("C-1", title="Título com acentuação"))
    target = tmp_path / "out.csv"
    ctx.import_export.export_csv(target)
    raw = target.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # BOM for Excel
    assert b"129,90" in raw and b";" in raw.splitlines()[0]
    result = ctx.import_export.import_csv(target)
    assert (result.created, result.skipped) == (0, 1)
    result = ctx.import_export.import_csv(target, mode="update")
    assert result.updated == 1 and not result.errors
    loaded = ctx.catalog.get(ctx.products.id_for_sku("C-1"))
    assert loaded.title == "Título com acentuação" and loaded.width_mm == 200


def test_csv_import_reports_bad_rows(ctx, tmp_path):
    source = tmp_path / "in.csv"
    source.write_text("sku;internal_name;price;marketplaces\n"
                      "OK-1;Produto bom;10,00;mercadolivre\n"
                      ";Sem sku;5;\n"
                      "BAD-2;Preço ruim;1,2,3;\n"
                      "BAD-3;Marketplace ruim;5;amazon\n", encoding="utf-8")
    result = ctx.import_export.import_csv(source)
    assert result.created == 1
    assert len(result.errors) == 3
    created = ctx.catalog.get(ctx.products.id_for_sku("OK-1"))
    assert created.enabled_marketplaces() == [Marketplace.MERCADO_LIVRE]


def test_csv_missing_required_columns(ctx, tmp_path):
    source = tmp_path / "in.csv"
    source.write_text("nome,preco\nA,1\n", encoding="utf-8")
    assert ctx.import_export.import_csv(source).errors


# ------------------------------------------------------------------ license
def test_trial_and_activation(ctx):
    manager = ctx.license
    status = manager.status()
    assert status.status == "trial" and status.trial_days_left == 30
    assert status.installation_id == manager.status().installation_id  # stable
    later = datetime.now() + timedelta(days=31)
    assert manager.status(today=later).status == "expired"
    with pytest.raises(LicenseError):
        manager.activate("MLA-BUSINESS-AAAA-BBBB-0000")
    key = PlaceholderKeyVerifier.make_key(Plan.PROFESSIONAL)
    active = manager.activate(key)
    assert active.status == "active" and active.plan is Plan.PROFESSIONAL
    assert active.masked_key.endswith(key[-4:])
    assert manager.deactivate().plan is Plan.TRIAL


def test_features_not_blocked_in_mvp_but_enforceable(ctx):
    assert ctx.license.is_enabled(Feature.WORKSPACES)  # enforcement off
    enforcing = LicenseManager(ctx.db, enforce=True)
    enforcing.activate(PlaceholderKeyVerifier.make_key(Plan.STARTER))
    assert enforcing.is_enabled(Feature.MERCADO_LIVRE)
    assert not enforcing.is_enabled(Feature.SHOPEE)


def test_settings_defaults_and_validation(ctx):
    assert ctx.settings.get("browser.channel") == "msedge"
    ctx.settings.set("automation.step_timeout_s", 45)
    assert ctx.settings.all()["automation.step_timeout_s"] == 45
    with pytest.raises(TypeError):
        ctx.settings.set("automation.step_timeout_s", "45")
    with pytest.raises(ValueError):
        ctx.settings.set("browser.channel", "firefox")
    with pytest.raises(KeyError):
        ctx.settings.set("nope", 1)
