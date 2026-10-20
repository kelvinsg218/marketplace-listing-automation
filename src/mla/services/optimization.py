"""Listing optimisation groundwork.

Implemented now (deterministic, no AI): `ListingQualityService.evaluate` scores how complete a prepared
listing is and lists what is missing. Contract only: `ListingOptimizer`, for future AI agents that
suggest titles/descriptions. Their output is stored as `ai_suggestions` (separate from client data and
from external observations), shown as hypotheses, and changes a listing only when the user accepts it;
the master product is never changed by a suggestion. Optimizers that send data outside the computer
are refused unless the user enabled `ai.external_providers_allowed`. Ollama is optional, never required.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

from mla.core.enums import ListingStatus
from mla.core.models import Listing
from mla.core.validation import MARKETPLACE_RULES
from mla.persistence.db import Database, now_iso

log = logging.getLogger(__name__)
SUGGESTIBLE = ("title", "description")


class SuggestionError(ValueError):
    pass


@dataclass
class QualityReport:
    score: int  # 0-100
    blocking: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)


@dataclass
class Suggestion:
    field: str
    proposed_value: str
    rationale: str = ""
    provider: str = ""
    model: str = ""
    current_value: str = ""
    listing_id: int | None = None
    product_id: int | None = None
    status: str = "pending"
    id: int | None = None
    created_at: str = ""


class ListingOptimizer(Protocol):
    """Contract for future suggestion agents (none ships in this version)."""
    name: str
    external: bool  # sends data to a service outside this computer

    def suggest(self, payload, quality: QualityReport) -> list[Suggestion]: ...


class ListingQualityService:
    def __init__(self, listings, products, compat_count=None):
        self.listings = listings  # ListingService
        self.products = products
        self.compat_count = compat_count

    def evaluate(self, listing: Listing) -> QualityReport:
        product = self.products.get(listing.product_id)
        payload = self.listings.payload(listing, product)
        report = self.listings.validate(listing, product)
        blocking = [i.message for i in report.issues if i.severity == "error"]
        checks: list[tuple[bool, str]] = []
        rules = MARKETPLACE_RULES.get(listing.marketplace)
        limit = rules.max_title if rules and rules.max_title else 60
        checks.append((len(payload.title) >= limit * 0.6,
                       f"Título curto ({len(payload.title)} de {limit} caracteres): inclua marca, modelo e "
                       "característica principal que o cliente informou."))
        checks.append((len(payload.description) >= 300,
                       "Descrição com menos de 300 caracteres: detalhe uso, medidas e conteúdo da embalagem."))
        checks.append((len(payload.images) >= 3, f"{len(payload.images)} imagem(ns): anúncios costumam usar ao menos 3."))
        checks.append((bool(product.gtin), "Sem GTIN/EAN no cadastro (algumas categorias exigem)."))
        checks.append((bool(product.brand and product.model), "Marca ou modelo não informados."))
        # the validation report already warns about a missing category; don't repeat it as a tip
        reported = {i.field for i in report.issues}
        category_ok = bool(payload.category_id)
        if "category_id" not in reported:
            checks.append((category_ok, "Categoria do marketplace ainda não definida."))
        checks.append((len(payload.attributes) >= 3, "Poucos atributos preenchidos para a categoria."))
        if self.compat_count is not None:
            checks.append((self.compat_count(product.id) > 0, "Nenhuma compatibilidade confirmada cadastrada."))
        passed = sum(1 for ok, _ in checks if ok)
        total = len(checks)
        if "category_id" in reported:  # still counts for the score
            total += 1
            passed += category_ok
        score = round(100 * passed / total) if total else 100
        if blocking:
            score = min(score, 40)
        return QualityReport(score, blocking, [text for ok, text in checks if not ok])


class SuggestionService:
    def __init__(self, db: Database, listings, settings):
        self.db = db
        self.listings = listings  # ListingService
        self.settings = settings

    def request(self, optimizer: ListingOptimizer, listing: Listing, quality: QualityReport) -> list[Suggestion]:
        if optimizer.external and not self.settings.get("ai.external_providers_allowed"):
            raise SuggestionError("Envio de dados para serviços externos de IA não foi autorizado nas "
                                  "Configurações; nada foi enviado.")
        payload = self.listings.payload(listing)
        stored = []
        for s in optimizer.suggest(payload, quality):
            if s.field not in SUGGESTIBLE or not s.proposed_value.strip():
                continue
            s.provider, s.listing_id, s.product_id = optimizer.name, listing.id, listing.product_id
            s.current_value = getattr(payload, s.field)
            s.created_at = now_iso()
            cur = self.db.execute(
                "INSERT INTO ai_suggestions (listing_id, product_id, field, current_value, proposed_value, rationale,"
                " provider, model, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
                (s.listing_id, s.product_id, s.field, s.current_value, s.proposed_value, s.rationale, s.provider,
                 s.model, s.created_at))
            s.id = cur.lastrowid
            stored.append(s)
        return stored

    def pending(self, listing_id: int) -> list[Suggestion]:
        return [Suggestion(field=r["field"], proposed_value=r["proposed_value"], rationale=r["rationale"],
                           provider=r["provider"], model=r["model"], current_value=r["current_value"],
                           listing_id=r["listing_id"], product_id=r["product_id"], status=r["status"], id=r["id"],
                           created_at=r["created_at"])
                for r in self.db.query("SELECT * FROM ai_suggestions WHERE listing_id = ? AND status = 'pending'"
                                       " ORDER BY id", (listing_id,))]

    def decide(self, suggestion_id: int, accept: bool) -> None:
        row = self.db.query_one("SELECT * FROM ai_suggestions WHERE id = ? AND status = 'pending'", (suggestion_id,))
        if row is None:
            raise SuggestionError("Sugestão não encontrada ou já decidida.")
        if accept:
            listing = self.listings.get(row["listing_id"])
            if listing is None or not (listing.status.in_preparation or listing.status in (
                    ListingStatus.FAILED, ListingStatus.CANCELLED, ListingStatus.NEEDS_ATTENTION)):
                raise SuggestionError("O anúncio não está em preparação; a sugestão não pode ser aplicada.")
            setattr(listing, row["field"], row["proposed_value"])  # listing override only, never the master
            self.listings.save(listing)
        self.db.execute("UPDATE ai_suggestions SET status = ?, decided_at = ? WHERE id = ?",
                        ("accepted" if accept else "rejected", now_iso(), suggestion_id))
