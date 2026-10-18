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
    """Lifecycle of one offer (product × marketplace × account).

    Preparation: draft → incomplete → ready (for review) → approved.
    Publication: queued → running → awaiting_review → published | failed | needs_attention | cancelled.
    Only a confirmed publication (proof read back from the marketplace) reaches PUBLISHED.
    """
    DRAFT = "draft"
    INCOMPLETE = "incomplete"
    READY = "ready"
    APPROVED = "approved"
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_review"
    PUBLISHED = "published"
    FAILED = "failed"
    NEEDS_ATTENTION = "needs_attention"
    CANCELLED = "cancelled"

    @property
    def label(self) -> str:
        return LISTING_LABELS[self]

    @property
    def in_preparation(self) -> bool:
        return self in PREPARATION_STATUSES

    @property
    def in_execution(self) -> bool:
        return self in (ListingStatus.QUEUED, ListingStatus.RUNNING, ListingStatus.AWAITING_REVIEW)


LISTING_LABELS = {
    ListingStatus.DRAFT: "Rascunho",
    ListingStatus.INCOMPLETE: "Incompleto",
    ListingStatus.READY: "Pronto para revisão",
    ListingStatus.APPROVED: "Aprovado",
    ListingStatus.QUEUED: "Na fila",
    ListingStatus.RUNNING: "Em execução",
    ListingStatus.AWAITING_REVIEW: "Aguardando revisão",
    ListingStatus.PUBLISHED: "Publicado confirmado",
    ListingStatus.FAILED: "Falha",
    ListingStatus.NEEDS_ATTENTION: "Requer intervenção",
    ListingStatus.CANCELLED: "Cancelado",
}
PREPARATION_STATUSES = frozenset({ListingStatus.DRAFT, ListingStatus.INCOMPLETE, ListingStatus.READY,
                                  ListingStatus.APPROVED})


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


class ConnectionStatus(StrEnum):
    """Result of the last account connection test."""
    UNKNOWN = "unknown"
    CONNECTED = "connected"
    LOGIN_REQUIRED = "login_required"
    EXPIRED = "expired"
    UNVERIFIED = "unverified"  # page opened, but this marketplace's login check is not mapped yet
    ERROR = "error"

    @property
    def label(self) -> str:
        return {ConnectionStatus.UNKNOWN: "Não testada", ConnectionStatus.CONNECTED: "Conectada",
                ConnectionStatus.LOGIN_REQUIRED: "Login necessário", ConnectionStatus.EXPIRED: "Sessão expirada",
                ConnectionStatus.UNVERIFIED: "Não verificada", ConnectionStatus.ERROR: "Falha de conexão"}[self]


class CommercialStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DISCONTINUED = "discontinued"

    @property
    def label(self) -> str:
        return {CommercialStatus.ACTIVE: "Ativo", CommercialStatus.INACTIVE: "Inativo",
                CommercialStatus.DISCONTINUED: "Fora de linha"}[self]


class DataSource(StrEnum):
    """Where a piece of information came from. Only CLIENT data is treated as fact by default."""
    CLIENT = "client"
    MANUFACTURER = "manufacturer"
    EXTERNAL = "external"
    AI = "ai"

    @property
    def label(self) -> str:
        return {DataSource.CLIENT: "Cliente", DataSource.MANUFACTURER: "Fabricante",
                DataSource.EXTERNAL: "Fonte externa", DataSource.AI: "Sugestão de IA"}[self]


class Verification(StrEnum):
    CONFIRMED = "confirmed"
    UNVERIFIED = "unverified"
    REJECTED = "rejected"

    @property
    def label(self) -> str:
        return {Verification.CONFIRMED: "Confirmada", Verification.UNVERIFIED: "Não verificada",
                Verification.REJECTED: "Rejeitada"}[self]


class ImportStatus(StrEnum):
    PLANNING = "planning"
    PLANNED = "planned"
    COMMITTING = "committing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    DISCARDED = "discarded"

    @property
    def label(self) -> str:
        return {ImportStatus.PLANNING: "Analisando", ImportStatus.PLANNED: "Aguardando confirmação",
                ImportStatus.COMMITTING: "Gravando", ImportStatus.COMPLETED: "Concluída",
                ImportStatus.CANCELLED: "Cancelada", ImportStatus.FAILED: "Falhou",
                ImportStatus.DISCARDED: "Descartada"}[self]


class ImportAction(StrEnum):
    """What the plan found for one source row (the user's decision is stored separately)."""
    CREATE = "create"
    UPDATE = "update"
    UNCHANGED = "unchanged"
    SKIP = "skip"
    ERROR = "error"
    REVIEW = "review"  # ambiguous extraction (e.g. PDF): needs the user's explicit decision

    @property
    def label(self) -> str:
        return {ImportAction.CREATE: "Novo", ImportAction.UPDATE: "Atualizar", ImportAction.UNCHANGED: "Sem mudanças",
                ImportAction.SKIP: "Ignorar", ImportAction.ERROR: "Erro", ImportAction.REVIEW: "Revisar"}[self]
