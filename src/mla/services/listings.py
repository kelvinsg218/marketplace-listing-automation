"""Prepared offers: one master product → many listings (marketplace × account).

A listing stores only what differs from the master product. Its preparation
state is derived from validating the *effective* content (master + overrides):
draft → incomplete → ready for review → approved (by the user). Approval is
tied to a fingerprint of the approved content: if the content changes, the
listing returns to "ready for review". Only the automation's confirmed
publication sets PUBLISHED; preparing or queueing never does.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field

from mla.automation.base import ListingPayload
from mla.automation.payload import build_payload
from mla.core.enums import CatalogStatus, ListingStatus, Marketplace
from mla.core.models import Listing, ListingRow, Product
from mla.core.validation import MARKETPLACE_RULES, ValidationReport
from mla.persistence.db import now_iso
from mla.persistence.listings import ListingExistsError, ListingRepository
from mla.persistence.repositories import AccountRepository, ProductRepository

log = logging.getLogger(__name__)
# fields the listing re-checks on its effective content (master errors on these are not inherited)
_EFFECTIVE_FIELDS = {"title", "description", "price", "stock", "images"}


class ListingError(ValueError):
    pass


@dataclass
class PrepareResult:
    created: list[int] = field(default_factory=list)
    existing: list[int] = field(default_factory=list)
    skipped: list[tuple[int, str]] = field(default_factory=list)  # (product id, reason)

    def summary(self) -> str:
        text = f"{len(self.created)} anúncio(s) preparado(s)"
        if self.existing:
            text += f", {len(self.existing)} já existia(m)"
        if self.skipped:
            text += f", {len(self.skipped)} não incluído(s)"
        return text


@dataclass
class ApprovalResult:
    approved: list[int] = field(default_factory=list)
    refused: list[tuple[int, str]] = field(default_factory=list)


class ListingService:
    def __init__(self, repo: ListingRepository, products: ProductRepository, accounts: AccountRepository,
                 catalog, images):
        self.repo = repo
        self.products = products
        self.accounts = accounts
        self.catalog = catalog  # CatalogService (validation with the user's category rules)
        self.images = images

    # ------------------------------------------------------------------ content
    def payload(self, listing: Listing, product: Product | None = None) -> ListingPayload:
        product = product or self._product(listing.product_id)
        return build_payload(product, listing.marketplace, self.images, listing)

    def validate(self, listing: Listing, product: Product | None = None) -> ValidationReport:
        product = product or self._product(listing.product_id)
        payload = self.payload(listing, product)
        marketplace = listing.marketplace
        report = ValidationReport()
        for issue in self.catalog.validate(product).issues:
            if issue.field in _EFFECTIVE_FIELDS and issue.severity == "error":
                continue
            if issue.marketplace is not None and issue.marketplace is not marketplace:
                continue
            report.issues.append(issue)
        if not payload.title:
            report.add("title", "Escreva o título do anúncio.")
        rules = MARKETPLACE_RULES.get(marketplace)
        if rules and rules.max_title and len(payload.title) > rules.max_title:
            report.add("title", f"Título com {len(payload.title)} caracteres; o limite no {marketplace.label} "
                                f"é {rules.max_title}" + ("." if rules.confirmed else " (limite ainda não confirmado "
                                                                                     "no formulário real)."))
        if not payload.description.strip():
            report.add("description", "Escreva a descrição do anúncio.")
        if payload.price_cents is None or payload.price_cents <= 0:
            report.add("price", "Informe um preço maior que zero.")
        if payload.stock <= 0:
            report.add("stock", "Estoque anunciado zerado.")
        if not payload.images:
            report.add("images", "Selecione pelo menos uma imagem.")
        elif rules and rules.max_images and len(payload.images) > rules.max_images:
            report.add("images", f"O {marketplace.label} usa no máximo {rules.max_images} imagens; "
                                 "as demais serão ignoradas.", "warning")
        if not payload.category_id:
            report.add("category_id", f"Categoria do {marketplace.label} não definida; será escolhida no formulário.",
                       "warning")
        account = self.accounts.get(listing.account_id)
        if account is None:
            report.add("account", "A conta do anúncio não existe mais.")
        elif not account.is_active:
            report.add("account", f"A conta {account.label} está desativada.")
        return report

    @staticmethod
    def fingerprint(payload: ListingPayload) -> str:
        data = {
            "title": payload.title, "description": payload.description, "price": payload.price_cents,
            "stock": payload.stock, "category_id": payload.category_id, "listing_type": payload.listing_type,
            "condition": payload.condition, "attributes": sorted(payload.attributes.items()),
            "images": [p.name for p in payload.images],
            "logistics": [payload.weight_g, payload.length_mm, payload.width_mm, payload.height_mm],
        }
        return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:32]

    def _derive(self, listing: Listing, product: Product) -> tuple[ListingStatus, ValidationReport]:
        report = self.validate(listing, product)
        errors = [i for i in report.issues if i.severity == "error"]
        if errors:
            status = ListingStatus.DRAFT if product.status is CatalogStatus.DRAFT else ListingStatus.INCOMPLETE
            return status, report
        if listing.status is ListingStatus.APPROVED and listing.approved_hash == \
                self.fingerprint(self.payload(listing, product)):
            return ListingStatus.APPROVED, report
        return ListingStatus.READY, report

    # ------------------------------------------------------------------ preparation
    def prepare(self, product_ids: list[int], marketplace: Marketplace, account_id: int) -> PrepareResult:
        account = self.accounts.get(account_id)
        if account is None or account.marketplace is not marketplace:
            raise ListingError("Escolha uma conta deste marketplace.")
        result = PrepareResult()
        for pid in dict.fromkeys(product_ids):
            product = self.products.get(pid)
            if product is None:
                result.skipped.append((pid, "Produto não encontrado."))
                continue
            existing = self.repo.get_for(pid, marketplace, account_id)
            if existing is not None:
                result.existing.append(existing.id)  # type: ignore[arg-type]
                continue
            listing = Listing(product_id=pid, marketplace=marketplace, account_id=account_id,
                              status=ListingStatus.DRAFT)
            listing.status, _ = self._derive(listing, product)
            try:
                self.repo.create(listing)
            except ListingExistsError:
                result.existing.append(self.repo.get_for(pid, marketplace, account_id).id)  # type: ignore[union-attr]
                continue
            result.created.append(listing.id)  # type: ignore[arg-type]
        log.info("anúncios preparados marketplace=%s conta=%s: %s", marketplace, account_id, result.summary())
        return result

    def save(self, listing: Listing) -> ValidationReport:
        """Store edited content and re-derive the preparation state."""
        current = self.repo.get(listing.id) if listing.id is not None else None
        if current is None:
            raise ListingError("Anúncio não encontrado.")
        self._ensure_editable(current)
        if listing.price_cents is not None and listing.price_cents < 0:
            raise ListingError("O preço não pode ser negativo.")
        if listing.stock is not None and listing.stock < 0:
            raise ListingError("O estoque não pode ser negativo.")
        product = self._product(listing.product_id)
        listing.status = current.status if current.status.in_preparation else ListingStatus.READY
        listing.approved_at, listing.approved_hash = current.approved_at, current.approved_hash
        listing.status, report = self._derive(listing, product)
        if listing.status is not ListingStatus.APPROVED:
            listing.approved_at, listing.approved_hash = None, ""
        self.repo.save_content(listing)
        return report

    def approve(self, listing_ids: list[int]) -> ApprovalResult:
        result = ApprovalResult()
        for lid in listing_ids:
            listing = self.repo.get(lid)
            if listing is None:
                continue
            if not listing.status.in_preparation:
                result.refused.append((lid, f"Situação atual: {listing.status.label}."))
                continue
            product = self._product(listing.product_id)
            report = self.validate(listing, product)
            errors = [i.message for i in report.issues if i.severity == "error"]
            if errors:
                self.repo.set_status(lid, ListingStatus.DRAFT if product.status is CatalogStatus.DRAFT
                                     else ListingStatus.INCOMPLETE)
                result.refused.append((lid, errors[0]))
                continue
            self.repo.set_status(lid, ListingStatus.APPROVED, now_iso(), self.fingerprint(self.payload(listing, product)))
            result.approved.append(lid)
        return result

    def revoke(self, listing_ids: list[int]) -> int:
        count = 0
        for lid in listing_ids:
            listing = self.repo.get(lid)
            if listing is not None and listing.status is ListingStatus.APPROVED:
                self.repo.set_status(lid, ListingStatus.READY)
                count += 1
        return count

    def refresh_for_product(self, product_id: int) -> None:
        """Re-derive listings still in preparation after the master product changed."""
        ids = self.repo.ids_in_preparation(product_id)
        if not ids:
            return
        product = self.products.get(product_id)
        if product is None:
            return
        for lid in ids:
            listing = self.repo.get(lid)
            if listing is None:
                continue
            status, _ = self._derive(listing, product)
            if status is not listing.status:
                approved = status is ListingStatus.APPROVED
                self.repo.set_status(lid, status, listing.approved_at if approved else None,
                                     listing.approved_hash if approved else "")

    def delete(self, listing_ids: list[int]) -> int:
        removable = []
        for lid in listing_ids:
            listing = self.repo.get(lid)
            if listing is None:
                continue
            if listing.status is ListingStatus.PUBLISHED or listing.status.in_execution:
                raise ListingError(f"Não é possível excluir um anúncio {listing.status.label.lower()}.")
            removable.append(lid)
        return self.repo.delete(removable)

    def block_reason(self, listing: Listing) -> str | None:
        """Why this listing cannot go to the queue now (None = it can)."""
        if listing.status is not ListingStatus.APPROVED:
            return f"Só anúncios aprovados vão para a fila (situação: {listing.status.label})."
        product = self.products.get(listing.product_id)
        if product is None:
            return "Produto não encontrado."
        status, report = self._derive(listing, product)
        if status is not ListingStatus.APPROVED:
            self.repo.set_status(listing.id, status)  # type: ignore[arg-type]
            errors = [i.message for i in report.issues if i.severity == "error"]
            return errors[0] if errors else "O conteúdo mudou depois da aprovação; revise e aprove de novo."
        return None

    # ------------------------------------------------------------------ queries
    def get(self, listing_id: int) -> Listing | None:
        return self.repo.get(listing_id)

    def rows(self, marketplace: Marketplace | None = None, account_id: int | None = None,
             statuses: list[ListingStatus] | None = None, text: str = "", limit: int = 200,
             offset: int = 0) -> list[ListingRow]:
        return self.repo.rows(marketplace, account_id, statuses, text, limit, offset)

    def count(self, marketplace: Marketplace | None = None, account_id: int | None = None,
              statuses: list[ListingStatus] | None = None, text: str = "") -> int:
        return self.repo.count(marketplace, account_id, statuses, text)

    def counts(self, marketplace: Marketplace | None = None, account_id: int | None = None) -> dict[ListingStatus, int]:
        return self.repo.counts_by_status(marketplace, account_id)

    # ------------------------------------------------------------------ helpers
    def _product(self, product_id: int) -> Product:
        product = self.products.get(product_id)
        if product is None:
            raise ListingError("O produto deste anúncio não existe mais.")
        return product

    @staticmethod
    def _ensure_editable(listing: Listing) -> None:
        if listing.status.in_execution:
            raise ListingError("Este anúncio está em execução; aguarde terminar ou cancele na tela Automações.")
        if listing.status is ListingStatus.PUBLISHED:
            raise ListingError("Anúncio já publicado: alterar anúncios existentes no marketplace ainda não é "
                               "suportado.")
