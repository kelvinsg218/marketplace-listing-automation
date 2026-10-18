import shutil

import pytest

from mla.core.enums import CommercialStatus, DataSource, ListingStatus, Marketplace, Verification
from mla.core.models import Compatibility, MissingMedia
from mla.core.validation import CategoryRule, gtin_valid, normalize_gtin, validate_product
from mla.persistence.db import Database, now_iso
from mla.persistence.migrator import MIGRATIONS_DIR, migrate
from mla.persistence.repositories import ProductQuery
from mla.services.compatibility import CompatibilityError, default_verification, parse_years
from mla.services.files import FileStore, FileStoreError


# ------------------------------------------------------------------ migration keeps old data
def test_upgrade_from_v3_keeps_products_listings_and_history(tmp_path):
    old_dir = tmp_path / "old_migs"
    old_dir.mkdir()
    for path in MIGRATIONS_DIR.glob("000[1-3]_*.sql"):
        shutil.copy(path, old_dir / path.name)
    db = Database(tmp_path / "mla.db")
    assert migrate(db, directory=old_dir) == [1, 2, 3]
    now = now_iso()
    db.execute("INSERT INTO products (internal_name, sku, title, price_cents, stock, status, created_at, updated_at)"
               " VALUES ('Antigo', 'OLD-1', 'Produto antigo', 990, 3, 'incomplete', ?, ?)", (now, now))
    pid = db.scalar("SELECT id FROM products")
    account = db.scalar("SELECT id FROM marketplace_accounts WHERE marketplace = 'simulado'")
    db.execute("INSERT INTO automation_jobs (label, created_at) VALUES ('j', ?)", (now,))
    db.execute("INSERT INTO automation_job_items (job_id, product_id, marketplace, account_id, status, created_at)"
               " VALUES (1, ?, 'simulado', ?, 'needs_attention', ?)", (pid, account, now))
    db.execute("INSERT INTO listings (product_id, marketplace, account_id, status, external_id, last_item_id,"
               " updated_at) VALUES (?, 'simulado', ?, 'failed', 'X1', 1, ?)", (pid, account, now))

    applied = migrate(db, backup_dir=tmp_path / "backups")
    assert applied[0] == 4
    assert list((tmp_path / "backups").glob("*.db")), "backup before migrating"
    row = db.query_one("SELECT * FROM products WHERE id = ?", (pid,))
    assert (row["sku"], row["title"], row["price_cents"], row["stock"]) == ("OLD-1", "Produto antigo", 990, 3)
    assert row["commercial_status"] == "active" and row["specs_json"] == "{}"
    listing = db.query_one("SELECT * FROM listings")
    assert listing["external_id"] == "X1" and listing["created_at"] == listing["updated_at"]
    assert listing["status"] == "needs_attention"  # was stored as plain failure before 0006
    assert db.scalar("SELECT COUNT(*) FROM automation_job_items") == 1
    db.close()


# ------------------------------------------------------------------ master fields
def test_master_fields_round_trip(ctx, complete_product):
    product = complete_product("MST-1", commercial_name="Suporte Pro", manufacturer_code="ACM-778",
                               gtin="7891234567895", supplier="Distribuidora Sul", cost_cents=7000,
                               promo_price_cents=11990, min_stock=2, unit="un",
                               commercial_status=CommercialStatus.ACTIVE, original_description="texto do ERP",
                               technical_description="Aço 1020", color="Preto", specs={"Carga máx.": "8 kg"},
                               custom_attributes={"Linha": "Office"}, manufacturer_refs="ACM-778-B",
                               internal_notes="Conferir embalagem", source="Importação #1")
    product.missing_media.append(MissingMedia("fotos/MST-1_2.jpg"))
    ctx.catalog.save(product)
    loaded = ctx.catalog.get(product.id)
    for name in ("commercial_name", "manufacturer_code", "gtin", "supplier", "cost_cents", "promo_price_cents",
                 "min_stock", "unit", "original_description", "technical_description", "color", "specs",
                 "custom_attributes", "manufacturer_refs", "internal_notes", "source"):
        assert getattr(loaded, name) == getattr(product, name), name
    assert [m.reference for m in loaded.missing_media] == ["fotos/MST-1_2.jpg"]
    summary = ctx.catalog.search(ProductQuery(text="ACM-778"))[0]
    assert summary.id == product.id and summary.missing_media == 1 and summary.gtin == "7891234567895"
    assert [s.id for s in ctx.catalog.search(ProductQuery(missing_media_only=True))] == [product.id]


def test_search_finds_variant_sku_and_paging(ctx, complete_product):
    for n in range(5):
        ctx.catalog.save(complete_product(f"PG-{n}"))
    assert ctx.products.count(ProductQuery(text="PG-")) == 5
    page1 = ctx.catalog.search(ProductQuery(text="PG-", order_by="sku", descending=False, limit=2))
    page3 = ctx.catalog.search(ProductQuery(text="PG-", order_by="sku", descending=False, limit=2, offset=4))
    assert [s.sku for s in page1] == ["PG-0", "PG-1"] and [s.sku for s in page3] == ["PG-4"]


def test_gtin_rules():
    assert gtin_valid("7891234567895")
    assert not gtin_valid("7891234567890")
    assert gtin_valid("96385074")  # GTIN-8
    assert normalize_gtin(" 789-1234567895 ") == "7891234567895"


def test_master_warnings_do_not_block(ctx, complete_product):
    product = complete_product("W-1", gtin="7891234567890", promo_price_cents=99999, cost_cents=50000,
                               min_stock=10, commercial_status=CommercialStatus.DISCONTINUED)
    report = ctx.catalog.save(product)
    fields = {i.field for i in report.issues if i.severity == "warning"}
    assert {"gtin", "promo_price", "price", "stock", "commercial_status"} <= fields
    assert product.status.value == "ready"


def test_category_rules_are_opt_in(ctx, complete_product):
    product = complete_product("CAT-1", category="Autopeças > Freios")
    assert not validate_product(product).catalog_errors()
    ctx.settings.set("catalog.category_rules", [{"category": "Autopeças", "required": ["gtin", "model"],
                                                  "requires_compatibility": True}])
    report = ctx.catalog.save(product)
    messages = " ".join(i.message for i in report.catalog_errors())
    assert "GTIN/EAN" in messages and "modelo" in messages and "compatibilidade" in messages
    assert product.status.value == "incomplete"
    product.gtin, product.model = "7891234567895", "Uno"
    ctx.compatibility.save(Compatibility(product.id, "Uno", brand="Fiat", verification=Verification.CONFIRMED))
    assert ctx.catalog.save(product).catalog_errors() == []
    assert CategoryRule("Autopeças").matches("autopeças > freios")


# ------------------------------------------------------------------ technical files
def test_file_store_dedups_and_refuses_unknown_types(tmp_path):
    store = FileStore(tmp_path / "files")
    manual = tmp_path / "manual.pdf"
    manual.write_bytes(b"%PDF-1.4 fake")
    first, second = store.import_file(manual), store.import_file(manual)
    assert first.filename == second.filename and first.original_name == "manual.pdf"
    script = tmp_path / "setup.bat"
    script.write_text("echo hi")
    with pytest.raises(FileStoreError):
        store.import_file(script)


# ------------------------------------------------------------------ compatibility
@pytest.mark.parametrize("text, expected", [
    ("2010-2015", (2010, 2015)), ("2010 a 2015", (2010, 2015)), ("2012", (2012, 2012)),
    ("2018+", (2018, None)), ("2018 em diante", (2018, None)), ("até 2014", (None, 2014)), ("", (None, None)),
])
def test_parse_years(text, expected):
    assert parse_years(text) == expected


def test_parse_years_rejects_garbage():
    with pytest.raises(CompatibilityError):
        parse_years("ano novo")


def test_compatibility_crud_dedup_and_verification(ctx, complete_product):
    product = complete_product("CMP-1")
    ctx.catalog.save(product)
    svc = ctx.compatibility
    c = svc.save(Compatibility(product.id, "Gol", brand="VW", year_from=2012, year_to=2016,
                               source=DataSource.CLIENT, verification=default_verification(DataSource.CLIENT)))
    assert c.verification is Verification.CONFIRMED
    ext = svc.save(Compatibility(product.id, "Uno", brand="Fiat", source=DataSource.EXTERNAL,
                                 source_detail="site do fabricante",
                                 verification=default_verification(DataSource.EXTERNAL)))
    assert ext.verification is Verification.UNVERIFIED
    with pytest.raises(CompatibilityError, match="já está cadastrada"):
        svc.save(Compatibility(product.id, "gol", brand="vw", year_from=2012, year_to=2016))
    with pytest.raises(CompatibilityError, match="ano inicial"):
        svc.save(Compatibility(product.id, "Palio", brand="Fiat", year_from=2015, year_to=2010))
    with pytest.raises(CompatibilityError, match="modelo"):
        svc.save(Compatibility(product.id, "  ", brand="Fiat"))
    assert svc.count(verification=Verification.UNVERIFIED) == 1
    svc.set_verification([ext.id], Verification.CONFIRMED)
    assert ctx.compatibility.repo.confirmed_count(product.id) == 2
    assert [x.model for x in svc.search("fiat")] == ["Uno"]
    summary = ctx.catalog.search(ProductQuery(text="CMP-1"))[0]
    assert summary.compat_count == 2


def test_replace_for_product_keeps_ids(ctx, complete_product):
    product = complete_product("CMP-2")
    ctx.catalog.save(product)
    svc = ctx.compatibility
    a = svc.save(Compatibility(product.id, "PS5", brand="Sony"))
    svc.save(Compatibility(product.id, "PS4", brand="Sony"))
    a.notes = "Edição digital também"
    svc.replace_for_product(product.id, [a, Compatibility(None, "Xbox Series X", brand="Microsoft")])
    items = svc.list_for_product(product.id)
    assert {i.model for i in items} == {"PS5", "Xbox Series X"}
    assert next(i for i in items if i.model == "PS5").id == a.id


def test_deleting_product_removes_its_compatibilities_and_listings(ctx, complete_product):
    product = complete_product("DEL-1")
    ctx.catalog.save(product)
    ctx.compatibility.save(Compatibility(product.id, "Modelo X"))
    account = ctx.accounts.default_for(Marketplace.SIMULATED)
    ctx.listings.prepare([product.id], Marketplace.SIMULATED, account.id)
    ctx.catalog.delete([product.id])
    assert ctx.compatibility.count() == 0
    assert ctx.listings.count() == 0
    assert ListingStatus.DRAFT.in_preparation
