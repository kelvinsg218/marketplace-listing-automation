import pytest

from mla.automation.queue import QueueManager
from mla.core.enums import ItemStatus, ListingStatus, Marketplace
from mla.core.models import MarketplaceAccount
from mla.services.listings import ListingError

SIM = Marketplace.SIMULATED
ML = Marketplace.MERCADO_LIVRE


@pytest.fixture
def sim_account(ctx):
    return ctx.accounts.default_for(SIM)


@pytest.fixture
def queue(ctx):
    return QueueManager(ctx.automation_repo, ctx.products, ctx.accounts)


def _prepared(ctx, complete_product, sim_account, sku="L-1", **overrides):
    product = complete_product(sku, **overrides)
    ctx.catalog.save(product)
    result = ctx.listings.prepare([product.id], SIM, sim_account.id)
    return product, ctx.listings.get(result.created[0])


def test_prepare_creates_one_listing_per_account_without_copying_master(ctx, complete_product, sim_account):
    product, listing = _prepared(ctx, complete_product, sim_account)
    assert listing.status is ListingStatus.READY
    assert listing.title == "" and listing.price_cents is None and listing.image_files == []
    again = ctx.listings.prepare([product.id], SIM, sim_account.id)
    assert again.created == [] and again.existing == [listing.id]
    second = ctx.account_service.save(MarketplaceAccount(SIM, "Loja 2"))
    other = ctx.listings.prepare([product.id], SIM, second.id)
    assert len(other.created) == 1
    assert ctx.listings.count(marketplace=SIM) == 2


def test_prepare_refuses_account_of_other_marketplace(ctx, complete_product, sim_account):
    product = complete_product("L-X")
    ctx.catalog.save(product)
    ml_account = ctx.accounts.default_for(ML)
    with pytest.raises(ListingError):
        ctx.listings.prepare([product.id], SIM, ml_account.id)


def test_incomplete_master_gives_incomplete_listing_and_overrides_fix_it(ctx, complete_product, sim_account):
    product, listing = _prepared(ctx, complete_product, sim_account, "L-2", title="", price_cents=None)
    assert listing.status is ListingStatus.INCOMPLETE
    listing.title, listing.price_cents = "Suporte para monitor articulado", 15990
    report = ctx.listings.save(listing)
    assert report.errors() == []
    stored = ctx.listings.get(listing.id)
    assert stored.status is ListingStatus.READY
    payload = ctx.listings.payload(stored)
    assert (payload.title, payload.price_cents) == ("Suporte para monitor articulado", 15990)


def test_effective_values_follow_master_until_overridden(ctx, complete_product, sim_account):
    product, listing = _prepared(ctx, complete_product, sim_account, "L-3")
    product.price_cents = 20000
    ctx.catalog.save(product)
    assert ctx.listings.payload(ctx.listings.get(listing.id)).price_cents == 20000
    row = ctx.listings.rows(SIM)[0]
    assert row.price_cents == 20000 and row.title == product.title


def test_title_limit_uses_listing_title(ctx, complete_product, sim_account):
    _, listing = _prepared(ctx, complete_product, sim_account, "L-4")
    listing.title = "x" * 80
    report = ctx.listings.save(listing)
    assert any(i.field == "title" for i in report.errors())
    assert ctx.listings.get(listing.id).status is ListingStatus.INCOMPLETE


def test_image_selection(ctx, complete_product, sim_account, png):
    product, listing = _prepared(ctx, complete_product, sim_account, "L-5")
    product.images.append(ctx.images.import_file(png()))
    ctx.catalog.save(product)
    second = product.images[1].filename
    listing.image_files = [second]
    ctx.listings.save(listing)
    payload = ctx.listings.payload(ctx.listings.get(listing.id))
    assert [p.name for p in payload.images] == [second]


def test_approval_is_revoked_when_content_changes(ctx, complete_product, sim_account):
    product, listing = _prepared(ctx, complete_product, sim_account, "L-6")
    assert ctx.listings.approve([listing.id]).approved == [listing.id]
    assert ctx.listings.get(listing.id).status is ListingStatus.APPROVED
    product.internal_notes = "nota interna não muda o anúncio"
    ctx.catalog.save(product)
    assert ctx.listings.get(listing.id).status is ListingStatus.APPROVED
    product.price_cents = 13990
    ctx.catalog.save(product)  # after_save hook re-derives preparation
    assert ctx.listings.get(listing.id).status is ListingStatus.READY


def test_cannot_approve_incomplete(ctx, complete_product, sim_account):
    _, listing = _prepared(ctx, complete_product, sim_account, "L-7", description="")
    result = ctx.listings.approve([listing.id])
    assert result.approved == [] and "descrição" in result.refused[0][1]


def test_only_approved_listings_reach_the_queue_and_queue_is_not_published(ctx, complete_product, sim_account,
                                                                            queue):
    _, ready = _prepared(ctx, complete_product, sim_account, "L-8")
    _, approved = _prepared(ctx, complete_product, sim_account, "L-9")
    ctx.listings.approve([approved.id])
    listings = [ctx.listings.get(ready.id), ctx.listings.get(approved.id)]
    result = queue.enqueue_listings(listings, ctx.listings.block_reason)
    assert result.queued == 1 and "aprovados" in result.skipped[0].reason
    assert ctx.listings.get(approved.id).status is ListingStatus.QUEUED
    assert ctx.listings.get(approved.id).title == ""  # publication columns only; content untouched
    counts = ctx.listings.counts()
    assert counts[ListingStatus.PUBLISHED] == 0
    with pytest.raises(ListingError, match="execução"):
        ctx.listings.save(ctx.listings.get(approved.id))
    with pytest.raises(ListingError):
        ctx.listings.delete([approved.id])


def test_marketplace_without_automation_is_refused(ctx, complete_product, queue):
    product = complete_product("L-10")
    ctx.catalog.save(product)
    account = ctx.accounts.default_for(ML)
    listing = ctx.listings.get(ctx.listings.prepare([product.id], ML, account.id).created[0])
    ctx.listings.approve([listing.id])
    result = queue.enqueue_listings([ctx.listings.get(listing.id)], ctx.listings.block_reason)
    assert result.queued == 0 and "não está disponível" in result.skipped[0].reason


def test_needs_attention_item_marks_listing_needs_attention(ctx, complete_product, sim_account, queue):
    _, listing = _prepared(ctx, complete_product, sim_account, "L-11")
    ctx.listings.approve([listing.id])
    result = queue.enqueue_listings([ctx.listings.get(listing.id)], ctx.listings.block_reason)
    item = ctx.automation_repo.items_for_job(result.job_id)[0]
    queue.finish_item(item, ItemStatus.NEEDS_ATTENTION, "Publicação não confirmada")
    assert ctx.listings.get(listing.id).status is ListingStatus.NEEDS_ATTENTION
    # after checking manually, the user can edit it again (back to preparation)
    report = ctx.listings.save(ctx.listings.get(listing.id))
    assert not report.errors() and ctx.listings.get(listing.id).status is ListingStatus.READY


def test_inactive_account_blocks(ctx, complete_product):
    second = ctx.account_service.save(MarketplaceAccount(SIM, "Loja inativa"))
    product = complete_product("L-12")
    ctx.catalog.save(product)
    listing = ctx.listings.get(ctx.listings.prepare([product.id], SIM, second.id).created[0])
    second.is_active = False
    ctx.account_service.save(second)
    report = ctx.listings.validate(listing)
    assert any(i.field == "account" for i in report.errors())


def test_rerun_from_history_uses_listing_flow_and_keeps_approval_guard(ctx, complete_product, sim_account, queue):
    product, listing = _prepared(ctx, complete_product, sim_account, "L-12")
    product.marketplace_data[SIM].enabled = False  # prepared on the Anúncios page only (demo bug 1)
    ctx.catalog.save(product)
    ctx.listings.approve([listing.id])
    first = queue.enqueue_listings([ctx.listings.get(listing.id)], ctx.listings.block_reason)
    item = ctx.automation_repo.items_for_job(first.job_id)[0]
    queue.finish_item(item, ItemStatus.FAILED, "Rejeitado na revisão")
    result = queue.requeue_item(item.id, ctx.listings.rerun_block_reason)
    assert result.queued == 1 and result.job_id != first.job_id
    # a change after the approval blocks a blind re-execution
    item = ctx.automation_repo.items_for_job(result.job_id)[0]
    queue.finish_item(item, ItemStatus.FAILED, "Rejeitado na revisão")
    product = ctx.products.get(product.id)
    product.price_cents = 99990
    ctx.catalog.save(product)
    blocked = queue.requeue_item(item.id, ctx.listings.rerun_block_reason)
    assert blocked.queued == 0 and "aprove de novo" in blocked.skipped[0].reason


def test_invalid_gtin_is_kept_in_catalog_but_blocks_the_listing(ctx, complete_product, sim_account):
    product, listing = _prepared(ctx, complete_product, sim_account, "L-13", gtin="7891234567890")  # bad digit
    assert ctx.catalog.get(product.id).gtin == "7891234567890"  # client data preserved
    assert listing.status is ListingStatus.INCOMPLETE
    assert ctx.listings.approve([listing.id]).approved == []
    product.gtin = "7891234567895"
    ctx.catalog.save(product)
    assert ctx.listings.get(listing.id).status is ListingStatus.READY
