"""ExecutionManager: runs queued items one at a time in a worker thread.

Per item: validate -> duplicates -> browser -> login -> form -> steps ->
read back -> HUMAN REVIEW -> publish (only if approved) -> confirm.

Qt-free on purpose (testable with plain pytest); the UI subscribes through
ExecutionHooks callbacks, which run on the worker thread.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from mla.automation.adapters import adapter_for
from mla.automation.base import (
    FORM_STEPS, AmbiguousStateError, AutomationError, BaseMarketplaceAdapter, ManualActionRequired,
    NotSupportedYet, StepError,
)
from mla.automation.browser import BrowserSessionManager, ProfileBusyError
from mla.automation.execution_logger import ExecutionLogger
from mla.automation.form_validator import FormValidator, Mismatch
from mla.automation.payload import build_payload
from mla.automation.queue import QueueManager
from mla.core.enums import ItemStatus, JobStatus, ListingStatus
from mla.core.models import ExecutionLog, JobItem, Listing
from mla.core.validation import validate_product
from mla.persistence.db import now_iso

log = logging.getLogger(__name__)
MAX_MANUAL_ROUNDS = 5


class Decision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    CONTINUE = "continue"
    CANCEL = "cancel"


@dataclass
class ReviewRequest:
    item: JobItem
    form: dict[str, str]
    mismatches: list[Mismatch] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    screenshot: str = ""


class ExecutionHooks(Protocol):
    def item_started(self, item: JobItem) -> None: ...
    def step_changed(self, item: JobItem, step: str) -> None: ...
    def item_finished(self, item: JobItem, status: ItemStatus, message: str) -> None: ...
    def review_requested(self, request: ReviewRequest) -> None: ...
    def manual_action_requested(self, item: JobItem, message: str) -> None: ...
    def log_added(self, entry: ExecutionLog) -> None: ...
    def idle(self) -> None: ...


class NullHooks:
    def __getattr__(self, _name):
        return lambda *args, **kwargs: None


class _Cancelled(Exception):
    pass


class _Stopped(Exception):
    pass


_NETWORK_MARKERS = ("net::err_", "ns_error_net", "ns_error_unknown_host", "ns_error_connection")


def _network_error(exc: Exception) -> bool:
    """Connection lost, DNS or proxy failures: safe to retry a step before the publish click."""
    text = str(exc).lower()
    return any(marker in text for marker in _NETWORK_MARKERS)


class ExecutionManager:
    def __init__(self, ctx, queue: QueueManager, hooks: ExecutionHooks | None = None, headless: bool = False):
        self.ctx = ctx
        self.queue = queue
        self.hooks = hooks or NullHooks()
        self.headless = headless
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._decision_event = threading.Event()
        self._decision: Decision | None = None
        self._lock = threading.Lock()
        self._current: JobItem | None = None
        self._cancel_current = False
        self._browser: BrowserSessionManager | None = None

    # ------------------------------------------------------------------ control (any thread)
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            self.wake()
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="mla-executor", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        self._wake.set()
        self._decision_event.set()
        if self._thread:
            self._thread.join(timeout)

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def wake(self) -> None:
        self._wake.set()

    @property
    def current_item(self) -> JobItem | None:
        return self._current

    def decide(self, item_id: int, decision: Decision) -> bool:
        with self._lock:
            if not self._current or self._current.id != item_id:
                return False
            self._decision = decision
            if decision is Decision.CANCEL:
                self._cancel_current = True
        self._decision_event.set()
        return True

    def cancel_items(self, item_ids: list[int]) -> None:
        with self._lock:
            if self._current and self._current.id in item_ids:
                self._cancel_current = True
                self._decision = Decision.CANCEL
                self._decision_event.set()

    # ------------------------------------------------------------------ worker
    def _settings(self, key: str):
        return self.ctx.settings.get(key)

    def _run(self) -> None:
        self._browser = BrowserSessionManager(self.ctx.paths.browser_profiles,
                                              channel=self._settings("browser.channel"), headless=self.headless)
        try:
            while not self._stop.is_set():
                item = self.ctx.automation_repo.next_queued_item()
                if item is None:
                    self._browser.close()
                    self.hooks.idle()
                    self._wake.wait(2.0)
                    self._wake.clear()
                    continue
                try:
                    self._process(item)
                except _Stopped:
                    log.info("execução interrompida no item %s (será retomada no próximo início)", item.id)
                    break
        finally:
            self._current = None
            try:
                self._browser.shutdown()
            except Exception as exc:
                log.warning("erro ao encerrar navegador: %s", exc)

    def _process(self, item: JobItem) -> None:
        repo = self.ctx.automation_repo
        with self._lock:
            self._current = item
            self._cancel_current = False
            self._decision = None
        self._decision_event.clear()
        logger = ExecutionLogger(repo, item, self.ctx.paths.artifacts, on_entry=self.hooks.log_added)
        item.attempts += 1
        repo.update_item(item.id, status=ItemStatus.RUNNING, started_at=now_iso(), attempts=item.attempts,
                         step="validate", error="")
        repo.set_job_status(item.job_id, JobStatus.RUNNING)
        self._listing(item, ListingStatus.RUNNING)
        item.status = ItemStatus.RUNNING
        self.hooks.item_started(item)
        adapter: BaseMarketplaceAdapter | None = None
        publishing = False
        try:
            self._step(item, logger, "validate")
            product = self.ctx.products.get(item.product_id) if item.product_id else None
            if product is None:
                raise StepError("O produto foi excluído do catálogo.", retryable=False)
            listing = repo.get_listing(item.product_id, item.marketplace, item.account_id)
            # the offer's effective content (master + this account's overrides) is what gets validated and sent
            report = self.ctx.listings.validate(listing, product) if listing else validate_product(product)
            errors = report.errors(item.marketplace)
            if errors:
                raise StepError("Cadastro incompleto: " + "; ".join(e.message for e in errors), retryable=False)

            self._step(item, logger, "duplicates")
            if listing and listing.status is ListingStatus.PUBLISHED:
                self._finish(item, ItemStatus.SKIPPED, f"Já publicado nesta conta ({listing.external_id}).", logger)
                return

            adapter_cls = adapter_for(item.marketplace)
            if not adapter_cls.implemented:
                raise NotSupportedYet(adapter_cls.pending_message if hasattr(adapter_cls, "pending_message")
                                      else "Marketplace ainda não integrado.")
            self._step(item, logger, "open_browser")
            account = self.ctx.accounts.get(item.account_id)
            if account is None or not account.is_active:
                raise StepError("A conta do marketplace não existe mais ou está desativada.", retryable=False)
            session = self._browser.open(account)
            payload = build_payload(product, item.marketplace, self.ctx.images, listing)
            timeout_ms = int(self._settings("automation.step_timeout_s")) * 1000
            adapter = adapter_cls(session.page, payload, logger, timeout_ms)
            logger.info(f"Navegador aberto com o perfil da conta {account.label}.")

            self._step(item, logger, "login")
            self._with_manual(item, logger, adapter, adapter.ensure_logged_in)
            self._step(item, logger, "open_form")
            self._attempt(item, logger, adapter, adapter.open_form)
            for key, method in FORM_STEPS:
                self._step(item, logger, key)
                self._attempt(item, logger, adapter, getattr(adapter, method))

            self._step(item, logger, "review")
            form = adapter.read_back()
            mismatches = FormValidator.compare(payload, form)
            for mismatch in mismatches:
                logger.warning(f"Divergência no formulário: {mismatch}")
            shot = logger.screenshot(adapter.page, "revisao", message="Formulário preenchido; aguardando revisão.")
            warnings = [i.message for i in report.warnings(item.marketplace)]
            self._step(item, logger, "await_approval")
            repo.update_item(item.id, status=ItemStatus.AWAITING_REVIEW)
            item.status = ItemStatus.AWAITING_REVIEW
            self._listing(item, ListingStatus.AWAITING_REVIEW)
            self.hooks.review_requested(ReviewRequest(item, form, mismatches, warnings, shot))
            decision = self._wait_decision({Decision.APPROVE, Decision.REJECT})
            if decision is Decision.REJECT:
                self._finish(item, ItemStatus.CANCELLED, "Rejeitado na revisão; nada foi publicado.", logger)
                return
            logger.info("Publicação aprovada pelo usuário.")
            repo.update_item(item.id, status=ItemStatus.RUNNING)
            item.status = ItemStatus.RUNNING

            self._step(item, logger, "publish")
            publishing = True
            self._with_manual(item, logger, adapter, adapter.publish)
            self._step(item, logger, "confirm", allow_cancel=False)  # the click happened: never "cancel" now
            result = adapter.confirm_publication()
            logger.screenshot(adapter.page, "publicado", message=f"Publicação confirmada: {result.external_id}")
            self._finish(item, ItemStatus.PUBLISHED, "", logger, result.external_id, result.url)
        except _Stopped:
            raise
        except _Cancelled:
            self._finish(item, ItemStatus.CANCELLED, "Cancelado pelo usuário.", logger)
        except AmbiguousStateError as exc:
            self._fail(item, logger, adapter, ItemStatus.NEEDS_ATTENTION, str(exc))
        except (StepError, NotSupportedYet, ProfileBusyError, AutomationError) as exc:
            status = ItemStatus.NEEDS_ATTENTION if publishing else ItemStatus.FAILED
            self._fail(item, logger, adapter, status, str(exc))
        except Exception as exc:  # Playwright errors, closed browser, unexpected bugs
            log.exception("erro inesperado no item %s", item.id)
            if publishing:
                message = (f"Erro durante a publicação ({exc.__class__.__name__}). Confira no marketplace se o "
                           "anúncio foi criado antes de reexecutar.")
                self._fail(item, logger, adapter, ItemStatus.NEEDS_ATTENTION, message)
            else:
                closed = "closed" in str(exc).lower()
                message = ("O navegador foi fechado durante a execução." if closed
                           else f"Erro inesperado: {exc.__class__.__name__}: {str(exc).splitlines()[0][:300]}")
                self._fail(item, logger, adapter, ItemStatus.FAILED, message)
        finally:
            with self._lock:
                self._current = None

    # ------------------------------------------------------------------ helpers
    def _step(self, item: JobItem, logger: ExecutionLogger, step: str, allow_cancel: bool = True) -> None:
        if self._stop.is_set() and allow_cancel:
            raise _Stopped()
        if self._cancel_current and allow_cancel:
            raise _Cancelled()
        logger.step = step
        item.step = step
        self.ctx.automation_repo.update_item(item.id, step=step)
        self.hooks.step_changed(item, step)

    def _attempt(self, item: JobItem, logger: ExecutionLogger, adapter: BaseMarketplaceAdapter, action) -> None:
        """Run one step with controlled retries; pause for manual action when the site asks for a human."""
        from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeout
        retries = int(self._settings("automation.max_retries"))
        failures = 0
        while True:
            try:
                self._with_manual(item, logger, adapter, lambda: (adapter.check_blockers(), action()))
                return
            except (PlaywrightError, StepError) as exc:
                if isinstance(exc, StepError) and not exc.retryable:
                    raise
                network = isinstance(exc, PlaywrightError) and _network_error(exc)
                if isinstance(exc, PlaywrightError) and not isinstance(exc, PlaywrightTimeout) and not network:
                    raise  # other browser errors are not retried blindly
                failures += 1
                if failures > retries:
                    reason = "falha de rede" if network else "tempo esgotado ou erro na etapa"
                    raise StepError(f"Etapa falhou após {failures} tentativas ({reason}): "
                                    f"{str(exc).splitlines()[0][:200]}", retryable=False) from exc
                logger.warning(f"Tentativa {failures} falhou; repetindo a etapa. ({str(exc).splitlines()[0][:200]})")

    def _with_manual(self, item: JobItem, logger: ExecutionLogger, adapter: BaseMarketplaceAdapter, action) -> None:
        rounds = 0
        while True:
            try:
                action()
                return
            except ManualActionRequired as exc:
                rounds += 1
                if rounds > MAX_MANUAL_ROUNDS:
                    raise StepError(f"A intervenção manual foi pedida {MAX_MANUAL_ROUNDS} vezes nesta etapa sem "
                                    f"resolver o bloqueio: {exc}", retryable=False) from exc
                message = str(exc)
                logger.warning(f"Intervenção manual necessária: {message}")
                logger.screenshot(adapter.page, "intervencao")
                self.hooks.manual_action_requested(item, message)
                self._wait_decision({Decision.CONTINUE})
                logger.info("Usuário concluiu a ação manual; retomando.")

    def _wait_decision(self, allowed: set[Decision]) -> Decision:
        while True:
            self._decision_event.wait(0.25)
            if self._stop.is_set():
                raise _Stopped()
            with self._lock:
                decision = self._decision
                if decision is not None:
                    self._decision = None
                    self._decision_event.clear()
            if decision is Decision.CANCEL:
                raise _Cancelled()
            if decision in allowed:
                return decision

    def _listing(self, item: JobItem, status: ListingStatus) -> None:
        if item.product_id is None:
            return
        existing = self.ctx.automation_repo.get_listing(item.product_id, item.marketplace, item.account_id)
        if existing and existing.status is ListingStatus.PUBLISHED:
            return
        self.ctx.automation_repo.upsert_listing(Listing(item.product_id, item.marketplace, item.account_id, status,
                                                        last_item_id=item.id))

    def _fail(self, item, logger, adapter, status: ItemStatus, message: str) -> None:
        if adapter is not None and self._settings("automation.screenshot_on_failure"):
            logger.screenshot(adapter.page, "falha", level="ERROR", message=message)
        else:
            logger.error(message)
        self._finish(item, status, message, logger)

    def _finish(self, item: JobItem, status: ItemStatus, message: str, logger: ExecutionLogger,
                external_id: str = "", url: str = "") -> None:
        if status is ItemStatus.PUBLISHED:
            logger.step = "done"
            logger.info(f"Anúncio publicado: {external_id} {url}")
        elif status in (ItemStatus.SKIPPED, ItemStatus.CANCELLED) and message:
            logger.info(message)
        self.queue.finish_item(item, status, "" if status is ItemStatus.PUBLISHED else message, external_id, url)
        item.status = status
        self.hooks.item_finished(item, status, message)
