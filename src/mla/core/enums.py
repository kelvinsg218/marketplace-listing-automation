from __future__ import annotations

from enum import StrEnum


class Marketplace(StrEnum):
    MERCADO_LIVRE = "mercadolivre"
    SHOPEE = "shopee"
    SIMULATED = "simulado"  # local HTML marketplace used for tests and demos

    @property
    def label(self) -> str:
        return {
            Marketplace.MERCADO_LIVRE: "Mercado Livre",
            Marketplace.SHOPEE: "Shopee",
            Marketplace.SIMULATED: "Marketplace simulado",
        }[self]

    @property
    def is_real(self) -> bool:
        return self is not Marketplace.SIMULATED


class Condition(StrEnum):
    NEW = "new"
    USED = "used"
    REFURBISHED = "refurbished"

    @property
    def label(self) -> str:
        return {Condition.NEW: "Novo", Condition.USED: "Usado", Condition.REFURBISHED: "Recondicionado"}[self]


class CatalogStatus(StrEnum):
    """Readiness of the product record itself, derived from validation."""
    DRAFT = "draft"
    INCOMPLETE = "incomplete"
    READY = "ready"

    @property
    def label(self) -> str:
        return {CatalogStatus.DRAFT: "Rascunho", CatalogStatus.INCOMPLETE: "Incompleto",
                CatalogStatus.READY: "Pronto"}[self]


class ListingStatus(StrEnum):
    """State of one product on one marketplace account."""
    DRAFT = "draft"
    INCOMPLETE = "incomplete"
    READY = "ready"
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_review"
    PUBLISHED = "published"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def label(self) -> str:
        return LISTING_LABELS[self]


LISTING_LABELS = {
    ListingStatus.DRAFT: "Rascunho",
    ListingStatus.INCOMPLETE: "Incompleto",
    ListingStatus.READY: "Pronto",
    ListingStatus.QUEUED: "Na fila",
    ListingStatus.RUNNING: "Em execução",
    ListingStatus.AWAITING_REVIEW: "Aguardando revisão",
    ListingStatus.PUBLISHED: "Publicado",
    ListingStatus.FAILED: "Falha",
    ListingStatus.CANCELLED: "Cancelado",
}


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

    @property
    def label(self) -> str:
        return {JobStatus.PENDING: "Pendente", JobStatus.RUNNING: "Em execução",
                JobStatus.PAUSED: "Pausado", JobStatus.COMPLETED: "Concluído",
                JobStatus.CANCELLED: "Cancelado"}[self]


class ItemStatus(StrEnum):
    """State of one product + marketplace + account combination inside a job."""
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_review"
    PUBLISHED = "published"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    NEEDS_ATTENTION = "needs_attention"  # ambiguous state: user must check the marketplace

    @property
    def label(self) -> str:
        return {ItemStatus.QUEUED: "Na fila", ItemStatus.RUNNING: "Em execução",
                ItemStatus.AWAITING_REVIEW: "Aguardando revisão", ItemStatus.PUBLISHED: "Publicado",
                ItemStatus.FAILED: "Falha", ItemStatus.CANCELLED: "Cancelado",
                ItemStatus.SKIPPED: "Ignorado", ItemStatus.NEEDS_ATTENTION: "Verificar manualmente"}[self]

    @property
    def is_terminal(self) -> bool:
        return self in TERMINAL_ITEM_STATUSES


TERMINAL_ITEM_STATUSES = frozenset({
    ItemStatus.PUBLISHED, ItemStatus.FAILED, ItemStatus.CANCELLED,
    ItemStatus.SKIPPED, ItemStatus.NEEDS_ATTENTION,
})
