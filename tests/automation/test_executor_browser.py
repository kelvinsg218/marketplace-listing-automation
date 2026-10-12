"""End-to-end runs against the bundled simulated marketplace in headless Edge.

Run only these:   pytest -m browser
Skip them:        pytest -m "not browser"
"""
from __future__ import annotations

import threading

import pytest

from mla.automation.adapters.simulated import SimulatedMarketplaceAdapter
from mla.automation.executor import Decision, ExecutionManager
from mla.automation.queue import QueueManager
from mla.core.enums import ItemStatus, ListingStatus, Marketplace

pytestmark = pytest.mark.browser
WAIT_S = 120


class Recorder:
    """Hooks that play the human: logs in, solves the CAPTCHA, approves or rejects the review."""

    def __init__(self, review_decision: Decision = Decision.APPROVE):
        self.executor: ExecutionManager | None = None
        self.review_decision = review_decision
        self.finished = threading.Event()
        self.results: list[tuple[int, ItemStatus, str]] = []
        self.reviews = []
        self.manual: list[str] = []
        self.steps: list[str] = []

    def item_started(self, item):
        pass

    def step_changed(self, item, step):
        self.steps.append(step)

    def item_finished(self, item, status, message):
        self.results.append((item.id, status, message))
        self.finished.set()

    def review_requested(self, request):
        self.reviews.append(request)
        self.executor.decide(request.item.id, self.review_decision)

    def manual_action_requested(self, item, message):
        self.manual.append(message)
        page = self.executor._browser.session.page  # hooks run on the worker thread
        if "login.html" in page.url:
            page.fill("#email", "teste@mla.local")
            page.fill("#password", "x")
            page.click("#login-submit")
            page.wait_for_url("**/sell.html*")
        elif page.locator("#captcha").is_visible():
            page.click("#captcha-ok")
        self.executor.decide(item.id, Decision.CONTINUE)

    def log_added(self, entry):
        pass

    def idle(self):
        pass


@pytest.fixture
def run(ctx):
    executors = []

    def runner(product_ids, decision=Decision.APPROVE):
        queue = QueueManager(ctx.automation_repo, ctx.products, ctx.accounts)
        result = queue.enqueue(product_ids)
        assert result.queued, result.skipped
        hooks = Recorder(decision)
        executor = ExecutionManager(ctx, queue, hooks, headless=True)
        hooks.executor = executor
        executors.append(executor)
        executor.start()
        assert hooks.finished.wait(WAIT_S), f"timeout; steps={hooks.steps}"
        return hooks, result

    yield runner
    for executor in executors:
        executor.stop(timeout=30)
    SimulatedMarketplaceAdapter.extra_query = ""


@pytest.fixture
def product(ctx, complete_product):
    p = complete_product("E2E-1", category="Informática", title="Suporte articulado para monitor 27")
    p.marketplace_data[Marketplace.SIMULATED].attributes = {"Modelo": "SA-27", "Cor": "Preto"}
    ctx.catalog.save(p)
    return p


def test_full_flow_login_review_publish(ctx, run, product):
    hooks, _ = run([product.id])
    item_id, status, message = hooks.results[0]
    assert status is ItemStatus.PUBLISHED, message
    assert any("Entre na sua conta" in m for m in hooks.manual)  # fresh profile -> manual login
    review = hooks.reviews[0]
    assert review.mismatches == []
    assert review.form["title"] == product.title and review.form["images"] == "1"
    assert review.form["category"] == "Informática"
    item = ctx.automation_repo.get_item(item_id)
    assert item.external_id.startswith("SIM-") and "listing.html" in item.url
    listing = ctx.automation_repo.get_listing(product.id, Marketplace.SIMULATED, item.account_id)
    assert listing.status is ListingStatus.PUBLISHED and listing.external_id == item.external_id
    steps = [e.step for e in ctx.automation_repo.logs_for_item(item_id)]
    assert "await_approval" in steps and steps[-1] == "done"
    shots = [e.screenshot for e in ctx.automation_repo.logs_for_item(item_id) if e.screenshot]
    assert shots and all((ctx.paths.artifacts / s).exists() for s in shots)
    # the same product cannot be published twice on the same account
    queue = QueueManager(ctx.automation_repo, ctx.products, ctx.accounts)
    again = queue.enqueue([product.id])
    assert again.queued == 0 and "Já publicado" in again.skipped[0].reason


def test_reject_in_review_publishes_nothing(ctx, run, product):
    hooks, _ = run([product.id], decision=Decision.REJECT)
    item_id, status, _ = hooks.results[0]
    assert status is ItemStatus.CANCELLED
    item = ctx.automation_repo.get_item(item_id)
    assert item.external_id == ""
    assert ctx.automation_repo.get_listing(product.id, Marketplace.SIMULATED, item.account_id).status \
        is ListingStatus.CANCELLED


def test_captcha_pauses_for_a_human(ctx, run, product):
    SimulatedMarketplaceAdapter.extra_query = "captcha=1"
    hooks, _ = run([product.id])
    assert hooks.results[0][1] is ItemStatus.PUBLISHED
    assert any("verificação" in m for m in hooks.manual)


def test_missing_required_category_attribute_fails_clearly(ctx, run, product):
    product.marketplace_data[Marketplace.SIMULATED].attributes = {}
    product.model = ""
    ctx.catalog.save(product)
    hooks, _ = run([product.id])
    item_id, status, message = hooks.results[0]
    assert status is ItemStatus.FAILED
    assert "exige o atributo 'Modelo'" in message
    assert not hooks.reviews  # never reached the review, nothing published
