import pytest

from mla.automation.base import ListingPayload
from mla.automation.form_validator import FormValidator
from mla.automation.payload import build_payload, compose_description
from mla.automation.queue import QueueManager
from mla.core.enums import ItemStatus, JobStatus, ListingStatus, Marketplace
from mla.core.models import Listing, Product, ProductGroup, ProductMarketplaceData


@pytest.fixture
def queue(ctx):
    return QueueManager(ctx.automation_repo, ctx.products, ctx.accounts)


@pytest.fixture
def ready(ctx, complete_product):
    def factory(sku="Q-1", **kw):
        product = complete_product(sku, **kw)
        ctx.catalog.save(product)
        return product
    return factory


def test_enqueue_creates_one_item_per_target(ctx, queue, ready):
    a, b = ready("A"), ready("B")
    result = queue.enqueue([a.id, b.id])
    assert result.queued == 2 and not result.skipped
    items = ctx.automation_repo.items_for_job(result.job_id)
    assert [(i.product_id, i.marketplace) for i in items] == [(a.id, Marketplace.SIMULATED), (b.id, Marketplace.SIMULATED)]
    assert items[0].product_name == a.internal_name and items[0].sku == "A"
    listing = ctx.automation_repo.get_listing(a.id, Marketplace.SIMULATED, items[0].account_id)
    assert listing.status is ListingStatus.QUEUED
    assert ctx.automation_repo.next_queued_item().id == items[0].id


def test_enqueue_skips_with_reasons(ctx, queue, ready):
    incomplete = Product(internal_name="Sem dados", sku="X-1")
    ctx.catalog.save(incomplete)
    no_market = ready("NM")
    no_market.marketplace_data.clear()
    ctx.catalog.save(no_market)
    real = ready("ML")
    real.marketplace_data[Marketplace.MERCADO_LIVRE] = ProductMarketplaceData(Marketplace.MERCADO_LIVRE, enabled=True)
    ctx.catalog.save(real)
    result = queue.enqueue([incomplete.id, no_market.id, real.id])
    reasons = {(s.product_name, s.marketplace): s.reason for s in result.skipped}
    assert "Nenhum marketplace ativado" in reasons[("Sem dados", None)]
    assert "Nenhum marketplace ativado" in reasons[(no_market.internal_name, None)]
    assert "ainda não está disponível" in reasons[(real.internal_name, Marketplace.MERCADO_LIVRE)]
    assert result.queued == 1  # real product still goes to the simulated marketplace


def test_invalid_product_is_not_enqueued(ctx, queue, ready):
    product = ready("INV", price_cents=None)
    ctx.catalog.save(product)
    result = queue.enqueue([product.id])
    assert result.queued == 0 and "preço" in result.skipped[0].reason.lower()


def test_duplicate_prevention(ctx, queue, ready):
    product = ready()
    assert queue.enqueue([product.id]).queued == 1
    again = queue.enqueue([product.id])
    assert again.queued == 0 and "fila" in again.skipped[0].reason
    item = ctx.automation_repo.next_queued_item()
    queue.finish_item(item, ItemStatus.PUBLISHED, external_id="SIM-1", url="file://x")
    third = queue.enqueue([product.id])
    assert third.queued == 0 and "Já publicado" in third.skipped[0].reason
    listing = ctx.automation_repo.get_listing(product.id, Marketplace.SIMULATED, item.account_id)
    assert listing.status is ListingStatus.PUBLISHED and listing.published_at


def test_failure_after_publish_keeps_listing_published(ctx, queue, ready):
    product = ready()
    queue.enqueue([product.id])
    item = ctx.automation_repo.next_queued_item()
    queue.finish_item(item, ItemStatus.PUBLISHED, external_id="SIM-9")
    ctx.automation_repo.upsert_listing(Listing(product.id, Marketplace.SIMULATED, item.account_id,
                                               ListingStatus.PUBLISHED, external_id="SIM-9"))
    queue.finish_item(item, ItemStatus.FAILED, "erro posterior")
    assert ctx.automation_repo.get_listing(product.id, Marketplace.SIMULATED, item.account_id).status \
        is ListingStatus.PUBLISHED


def test_group_enqueue_uses_group_marketplaces_and_order(ctx, queue, ready):
    a, b = ready("GA"), ready("GB")
    group = ctx.groups.save(ProductGroup(name="Lote", product_ids=[b.id, a.id], marketplaces=[Marketplace.SIMULATED]))
    result = queue.enqueue_group(group)
    job = ctx.automation_repo.get_job(result.job_id)
    assert job.kind == "group" and job.group_id == group.id
    assert [i.product_id for i in ctx.automation_repo.items_for_job(job.id)] == [b.id, a.id]
    empty = ctx.groups.save(ProductGroup(name="Sem marketplace", product_ids=[a.id]))
    assert queue.enqueue_group(empty).queued == 0


def test_pause_resume_cancel(ctx, queue, ready):
    a, b = ready("P1"), ready("P2")
    job_id = queue.enqueue([a.id, b.id]).job_id
    queue.pause(job_id)
    assert ctx.automation_repo.next_queued_item() is None  # paused jobs are not picked
    queue.resume(job_id)
    assert ctx.automation_repo.next_queued_item() is not None
    assert queue.cancel(job_id) == []
    assert ctx.automation_repo.get_job(job_id).status is JobStatus.CANCELLED
    assert {i.status for i in ctx.automation_repo.items_for_job(job_id)} == {ItemStatus.CANCELLED}
    assert ctx.automation_repo.next_queued_item() is None


def test_cancel_with_running_item_returns_it(ctx, queue, ready):
    a, b = ready("R1"), ready("R2")
    job_id = queue.enqueue([a.id, b.id]).job_id
    first = ctx.automation_repo.items_for_job(job_id)[0]
    ctx.automation_repo.update_item(first.id, status=ItemStatus.RUNNING)
    assert queue.cancel(job_id) == [first.id]
    assert ctx.automation_repo.get_job(job_id).status is JobStatus.PAUSED


def test_recovery_after_restart(ctx, queue, ready):
    a, b, c = ready("C1"), ready("C2"), ready("C3")
    job_id = queue.enqueue([a.id, b.id, c.id]).job_id
    ctx.automation_repo.set_job_status(job_id, JobStatus.RUNNING)
    i1, i2, i3 = ctx.automation_repo.items_for_job(job_id)
    ctx.automation_repo.update_item(i1.id, status=ItemStatus.RUNNING, step="images")
    ctx.automation_repo.update_item(i2.id, status=ItemStatus.RUNNING, step="publish")
    ctx.automation_repo.update_item(i3.id, status=ItemStatus.AWAITING_REVIEW, step="await_approval")
    assert queue.recover_after_restart() == 3
    r1, r2, r3 = (ctx.automation_repo.get_item(i.id) for i in (i1, i2, i3))
    assert r1.status is ItemStatus.QUEUED and r3.status is ItemStatus.QUEUED
    assert r2.status is ItemStatus.NEEDS_ATTENTION and "Confira no marketplace" in r2.error
    assert ctx.automation_repo.get_job(job_id).status is JobStatus.PAUSED
    assert ctx.automation_repo.logs_for_item(i2.id)[0].level == "ERROR"


def test_requeue_finished_item(ctx, queue, ready):
    product = ready()
    queue.enqueue([product.id])
    item = ctx.automation_repo.next_queued_item()
    assert queue.requeue_item(item.id).queued == 0  # still queued -> refused
    queue.finish_item(item, ItemStatus.FAILED, "timeout")
    result = queue.requeue_item(item.id)
    assert result.queued == 1 and result.job_id != item.job_id


def test_history_survives_product_deletion(ctx, queue, ready):
    product = ready("HIST")
    queue.enqueue([product.id])
    item = ctx.automation_repo.next_queued_item()
    queue.finish_item(item, ItemStatus.FAILED, "falhou")
    ctx.catalog.delete([product.id])
    rows = ctx.automation_repo.history()
    assert rows[0].sku == "HIST" and rows[0].product_name == product.internal_name and rows[0].product_id is None


# ------------------------------------------------------------------ payload and form comparison
def test_payload_orders_main_image_first_and_merges_attributes(ctx, complete_product, png):
    product = complete_product(brand="Acme", model="X1")
    second = ctx.images.import_file(png(900, 900))
    second.is_main = True
    product.images[0].is_main = False
    product.images.append(second)
    product.marketplace_data[Marketplace.SIMULATED].price_cents = 9990
    product.features = "Aço carbono\n- Ajuste de altura"
    payload = build_payload(product, Marketplace.SIMULATED, ctx.images)
    assert payload.images[0].name == second.filename
    assert payload.price_cents == 9990 and payload.price_text == "99,90"
    assert payload.attributes == {"Marca": "Acme", "Modelo": "X1"}
    assert "- Ajuste de altura" in compose_description(product)


def test_form_validator_detects_divergences():
    payload = ListingPayload(product_id=1, sku="S", title="Título certo", category="", category_id="",
                             listing_type="", condition="new", description="Desc", price_cents=12990, stock=3,
                             weight_g=1, length_mm=1, width_mm=1, height_mm=1, images=[])
    ok = {"title": "Título  certo", "price": "129,90", "stock": "3", "description": "Desc", "images": "0"}
    assert FormValidator.compare(payload, ok) == []
    bad = {**ok, "title": "Título cortad", "price": "12,99", "stock": "30"}
    assert [m.field for m in FormValidator.compare(payload, bad)] == ["Título", "Preço", "Estoque"]
