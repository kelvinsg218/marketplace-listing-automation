"""Persistent job queue: enqueue, pause/resume/cancel, duplicate prevention, crash recovery."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from mla.automation.adapters import adapter_for
from mla.core.enums import ItemStatus, JobStatus, ListingStatus, Marketplace
from mla.core.models import ExecutionLog, Job, JobItem, Listing
from mla.core.validation import validate_product
from mla.persistence.db import now_iso
from mla.persistence.repositories import AccountRepository, AutomationRepository, ProductRepository

log = logging.getLogger(__name__)
PUBLISH_STEPS = {"publish", "confirm"}


@dataclass
class Skipped:
    product_id: int
    product_name: str
    marketplace: Marketplace | None
    reason: str


@dataclass
class EnqueueResult:
    job_id: int | None = None
    queued: int = 0
    skipped: list[Skipped] = field(default_factory=list)

    def summary(self) -> str:
        text = f"{self.queued} na fila"
        if self.skipped:
            text += f", {len(self.skipped)} não incluído(s)"
        return text


class QueueManager:
    def __init__(self, repo: AutomationRepository, products: ProductRepository, accounts: AccountRepository):
        self.repo = repo
        self.products = products
        self.accounts = accounts

    # ------------------------------------------------------------------ enqueue
    def enqueue(self, product_ids: list[int], marketplaces: list[Marketplace] | None = None, label: str = "",
                kind: str = "product", group_id: int | None = None,
                account_ids: dict[Marketplace, int] | None = None) -> EnqueueResult:
        """One item per product × marketplace × account. `marketplaces=None` uses each product's enabled ones."""
        result = EnqueueResult()
        items: list[JobItem] = []
        seen: set[tuple[int, Marketplace, int]] = set()
        for pid in product_ids:
            product = self.products.get(pid)
            if product is None:
                continue
            targets = marketplaces if marketplaces is not None else product.enabled_marketplaces()
            if not targets:
                result.skipped.append(Skipped(pid, product.internal_name, None,
                                              "Nenhum marketplace ativado no cadastro do produto."))
                continue
            report = validate_product(product)
            for marketplace in targets:
                reason = self._block_reason(product, marketplace, report)
                account = self._account(marketplace, account_ids)
                if reason is None and account is None:
                    reason = f"Nenhuma conta ativa do {marketplace.label}."
                if reason is None:
                    key = (pid, marketplace, account.id)
                    if key in seen:
                        continue
                    seen.add(key)
                    reason = self._duplicate_reason(pid, marketplace, account.id)
                if reason:
                    result.skipped.append(Skipped(pid, product.internal_name, marketplace, reason))
                    continue
                items.append(JobItem(job_id=0, product_id=pid, marketplace=marketplace, account_id=account.id,
                                     product_name=product.internal_name, sku=product.sku))
        if not items:
            return result
        if not label:
            label = items[0].product_name if len(product_ids) == 1 else f"{len(product_ids)} produtos"
        job = Job(label=label, kind=kind if len(product_ids) > 1 or kind == "group" else "product",
                  group_id=group_id)
        result.job_id = self.repo.create_job(job, items)
        result.queued = len(items)
        for item in items:
            self.repo.upsert_listing(Listing(item.product_id, item.marketplace, item.account_id,
                                             ListingStatus.QUEUED, last_item_id=item.id))
        log.info("job %s criado com %s itens", job.id, len(items))
        return result

    def _block_reason(self, product, marketplace: Marketplace, report) -> str | None:
        if not adapter_for(marketplace).implemented:
            return f"A automação do {marketplace.label} ainda não está disponível nesta versão."
        if marketplace not in product.enabled_marketplaces():
            return f"{marketplace.label} não está ativado no cadastro do produto."
        errors = report.errors(marketplace)
        if errors:
            return errors[0].message + (f" (+{len(errors) - 1} pendência(s))" if len(errors) > 1 else "")
        return None

    def _account(self, marketplace: Marketplace, account_ids: dict[Marketplace, int] | None):
        if account_ids and marketplace in account_ids:
            account = self.accounts.get(account_ids[marketplace])
            return account if account and account.is_active else None
        return self.accounts.default_for(marketplace)

    def _duplicate_reason(self, product_id: int, marketplace: Marketplace, account_id: int) -> str | None:
        listing = self.repo.get_listing(product_id, marketplace, account_id)
        if listing and listing.status is ListingStatus.PUBLISHED:
            return "Já publicado nesta conta" + (f" ({listing.external_id})." if listing.external_id else ".")
        active = self.repo.active_item_for_target(product_id, marketplace, account_id)
        if active:
            return f"Já está na fila ({active.status.label.lower()})."
        return None

    def enqueue_group(self, group, marketplaces: list[Marketplace] | None = None) -> EnqueueResult:
        targets = marketplaces or group.marketplaces
        if not targets:
            result = EnqueueResult()
            result.skipped.append(Skipped(0, group.name, None, "Selecione ao menos um marketplace para o grupo."))
            return result
        return self.enqueue(group.product_ids, targets, label=f"Grupo {group.name}", kind="group",
                            group_id=group.id)

    def requeue_item(self, item_id: int) -> EnqueueResult:
        """Safe re-execution of a finished item: same target, new job, same duplicate checks."""
        item = self.repo.get_item(item_id)
        if item is None or item.product_id is None:
            result = EnqueueResult()
            result.skipped.append(Skipped(0, "", None, "O produto desta execução não existe mais."))
            return result
        if not item.status.is_terminal:
            result = EnqueueResult()
            result.skipped.append(Skipped(item.product_id, item.product_name, item.marketplace,
                                          "A execução ainda está em andamento."))
            return result
        return self.enqueue([item.product_id], [item.marketplace], label=f"Reexecução: {item.product_name}",
                            account_ids={item.marketplace: item.account_id})

    # ------------------------------------------------------------------ control
    def pause(self, job_id: int) -> None:
        job = self.repo.get_job(job_id)
        if job and job.status in (JobStatus.PENDING, JobStatus.RUNNING):
            self.repo.set_job_status(job_id, JobStatus.PAUSED)

    def resume(self, job_id: int) -> None:
        job = self.repo.get_job(job_id)
        if job and job.status is JobStatus.PAUSED:
            self.repo.set_job_status(job_id, JobStatus.PENDING)

    def cancel(self, job_id: int) -> list[int]:
        """Cancel queued items. Returns ids of items still running (the executor must stop them)."""
        running: list[int] = []
        for item in self.repo.items_for_job(job_id):
            if item.status is ItemStatus.QUEUED:
                self.finish_item(item, ItemStatus.CANCELLED, "Cancelado pelo usuário.")
            elif item.status in (ItemStatus.RUNNING, ItemStatus.AWAITING_REVIEW):
                running.append(item.id)
        if not running:
            self.repo.set_job_status(job_id, JobStatus.CANCELLED)
        else:
            self.repo.set_job_status(job_id, JobStatus.PAUSED)
        return running

    def finish_item(self, item: JobItem, status: ItemStatus, error: str = "", external_id: str = "",
                    url: str = "") -> None:
        now = now_iso()
        self.repo.update_item(item.id, status=status, error=error, external_id=external_id, url=url,
                              finished_at=now)
        listing_status = {
            ItemStatus.PUBLISHED: ListingStatus.PUBLISHED, ItemStatus.FAILED: ListingStatus.FAILED,
            ItemStatus.NEEDS_ATTENTION: ListingStatus.FAILED, ItemStatus.CANCELLED: ListingStatus.CANCELLED,
        }.get(status)
        if item.product_id is not None and listing_status is not None:
            existing = self.repo.get_listing(item.product_id, item.marketplace, item.account_id)
            if not (existing and existing.status is ListingStatus.PUBLISHED and status is not ItemStatus.PUBLISHED):
                self.repo.upsert_listing(Listing(
                    item.product_id, item.marketplace, item.account_id, listing_status, external_id=external_id,
                    url=url, published_at=now if status is ItemStatus.PUBLISHED else None, last_item_id=item.id))
        self.complete_job_if_done(item.job_id)

    def complete_job_if_done(self, job_id: int) -> None:
        job = self.repo.get_job(job_id)
        if job is None or job.status in (JobStatus.COMPLETED, JobStatus.CANCELLED):
            return
        items = self.repo.items_for_job(job_id)
        if items and all(i.status.is_terminal for i in items):
            cancelled = all(i.status in (ItemStatus.CANCELLED, ItemStatus.SKIPPED) for i in items)
            self.repo.set_job_status(job_id, JobStatus.CANCELLED if cancelled else JobStatus.COMPLETED)

    # ------------------------------------------------------------------ recovery
    def recover_after_restart(self) -> int:
        """Called at startup before the executor runs. Returns the number of items touched."""
        touched = 0
        for item in self.repo.items_with_status([ItemStatus.RUNNING, ItemStatus.AWAITING_REVIEW]):
            touched += 1
            if item.status is ItemStatus.RUNNING and item.step in PUBLISH_STEPS:
                message = ("O MLA foi fechado durante a publicação. Confira no marketplace se o anúncio foi "
                           "criado antes de reexecutar.")
                self._log(item, "ERROR", message)
                self.finish_item(item, ItemStatus.NEEDS_ATTENTION, message)
            else:
                self._log(item, "WARNING", "Execução interrompida pelo fechamento do aplicativo; item voltou para a fila.")
                self.repo.update_item(item.id, status=ItemStatus.QUEUED, step="")
                if item.product_id is not None:
                    self.repo.upsert_listing(Listing(item.product_id, item.marketplace, item.account_id,
                                                     ListingStatus.QUEUED, last_item_id=item.id))
        for job in self.repo.list_jobs([JobStatus.RUNNING]):
            self.repo.set_job_status(job.id, JobStatus.PAUSED)
            self.complete_job_if_done(job.id)
        return touched

    def _log(self, item: JobItem, level: str, message: str) -> None:
        self.repo.add_log(ExecutionLog(level=level, message=message, step=item.step, job_id=item.job_id,
                                       item_id=item.id, product_id=item.product_id,
                                       marketplace=item.marketplace.value))
