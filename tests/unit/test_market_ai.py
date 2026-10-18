"""Groundwork for market intelligence and optimisation: provenance, consent and user control."""
import pytest

from mla.core.enums import ListingStatus, Marketplace
from mla.services.market import MarketError, Observation, Reference
from mla.services.optimization import Suggestion, SuggestionError


@pytest.fixture
def prepared(ctx, complete_product):
    product = complete_product("MK-1")
    ctx.catalog.save(product)
    account = ctx.accounts.default_for(Marketplace.SIMULATED)
    listing = ctx.listings.get(ctx.listings.prepare([product.id], Marketplace.SIMULATED, account.id).created[0])
    return product, listing


def test_references_and_manual_price_comparison(ctx, prepared):
    product, _ = prepared
    with pytest.raises(MarketError, match="HTTPS"):
        ctx.market.add_reference(Reference("http://exemplo.com/anuncio", product.id))
    a = ctx.market.add_reference(Reference("https://exemplo.com/anuncio-a", product.id, title="Concorrente A"))
    b = ctx.market.add_reference(Reference("https://exemplo.com/anuncio-b", product.id))
    ctx.market.record(a.id, Observation("price", value_cents=11990, collected_at="2026-10-01T10:00:00"))
    ctx.market.record(a.id, Observation("price", value_cents=10990, collected_at="2026-10-15T10:00:00"))
    ctx.market.record(b.id, Observation("price", value_cents=13990, collected_at="2026-10-16T10:00:00"))
    comparison = ctx.market.price_comparison(product.id, product.price_cents)
    assert sorted(comparison.observed) == [10990, 13990]  # only the latest price of each reference
    assert comparison.lowest == 10990 and comparison.oldest == "2026-10-15T10:00:00"
    with pytest.raises(MarketError):
        ctx.market.record(a.id, Observation("price", value_cents=0))


def test_collector_without_reviewed_terms_is_refused(ctx, prepared):
    product, _ = prepared
    ref = ctx.market.add_reference(Reference("https://exemplo.com/x", product.id))

    class Collector:
        name, source, terms_reviewed = "teste", "collector", False

        def collect(self, reference):
            raise AssertionError("must not run")

    with pytest.raises(MarketError, match="termos"):
        ctx.market.collect_with(Collector(), ref)
    Collector.terms_reviewed = True
    Collector.collect = lambda self, reference: [Observation("title", value_text="Título do concorrente")]
    stored = ctx.market.collect_with(Collector(), ref)
    assert stored[0].source == "collector" and stored[0].collector == "teste" and stored[0].collected_at


def test_quality_score_is_deterministic(ctx, prepared):
    product, listing = prepared
    before = ctx.quality.evaluate(listing)
    assert not before.blocking and any("GTIN" in text for text in before.improvements)
    product.gtin, product.model = "7891234567895", "SM-27"
    ctx.catalog.save(product)
    after = ctx.quality.evaluate(ctx.listings.get(listing.id))
    assert after.score > before.score and not any("GTIN" in text for text in after.improvements)
    assert ctx.quality.evaluate(ctx.listings.get(listing.id)).score == after.score


class FakeOptimizer:
    name, external = "fake-local", False

    def suggest(self, payload, quality):
        return [Suggestion("title", payload.title + " com ajuste de altura", rationale="Detalhe do cadastro"),
                Suggestion("price", "1,00")]  # not suggestible: ignored


def test_suggestions_only_change_listing_when_accepted(ctx, prepared):
    product, listing = prepared
    stored = ctx.suggestions.request(FakeOptimizer(), listing, ctx.quality.evaluate(listing))
    assert [s.field for s in stored] == ["title"]
    assert ctx.listings.get(listing.id).title == ""  # nothing applied yet
    ctx.suggestions.decide(stored[0].id, accept=True)
    assert ctx.listings.get(listing.id).title.endswith("com ajuste de altura")
    assert ctx.products.get(product.id).title == product.title, "master product never changed by a suggestion"
    assert ctx.suggestions.pending(listing.id) == []
    with pytest.raises(SuggestionError):
        ctx.suggestions.decide(stored[0].id, accept=False)


def test_external_ai_needs_consent(ctx, prepared):
    _, listing = prepared

    class External(FakeOptimizer):
        name, external = "nuvem", True

    with pytest.raises(SuggestionError, match="não foi autorizado"):
        ctx.suggestions.request(External(), listing, ctx.quality.evaluate(listing))
    ctx.settings.set("ai.external_providers_allowed", True)
    assert ctx.suggestions.request(External(), listing, ctx.quality.evaluate(listing))
    assert ListingStatus.READY.in_preparation
