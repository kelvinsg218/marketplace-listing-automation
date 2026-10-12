from __future__ import annotations

from dataclasses import dataclass, field

from mla.core.enums import CatalogStatus, ItemStatus, JobStatus, ListingStatus, Marketplace
from mla.core.models import JobItem
from mla.persistence.repositories import AutomationRepository, ProductRepository


@dataclass
class DashboardStats:
    total_products: int = 0
    by_catalog_status: dict[CatalogStatus, int] = field(default_factory=dict)
    published: int = 0
    pending: int = 0           # queued + running + awaiting review
    awaiting_review: int = 0
    active_jobs: int = 0
    failures: int = 0
    by_marketplace: dict[Marketplace, dict[ListingStatus, int]] = field(default_factory=dict)
    recent: list[JobItem] = field(default_factory=list)


class DashboardService:
    def __init__(self, products: ProductRepository, automation: AutomationRepository):
        self.products = products
        self.automation = automation

    def stats(self) -> DashboardStats:
        by_status = self.products.count_by_status()
        items = self.automation.count_items_by_status()
        listings = self.automation.listing_counts()
        by_marketplace: dict[Marketplace, dict[ListingStatus, int]] = {}
        for (marketplace, status), n in listings.items():
            by_marketplace.setdefault(marketplace, {})[status] = n
        published = sum(n for (_, s), n in listings.items() if s is ListingStatus.PUBLISHED)
        return DashboardStats(
            total_products=sum(by_status.values()),
            by_catalog_status=by_status,
            published=published,
            pending=items[ItemStatus.QUEUED] + items[ItemStatus.RUNNING] + items[ItemStatus.AWAITING_REVIEW],
            awaiting_review=items[ItemStatus.AWAITING_REVIEW],
            active_jobs=len(self.automation.list_jobs([JobStatus.PENDING, JobStatus.RUNNING, JobStatus.PAUSED])),
            failures=items[ItemStatus.FAILED] + items[ItemStatus.NEEDS_ATTENTION],
            by_marketplace=by_marketplace,
            recent=self.automation.history(limit=8),
        )
