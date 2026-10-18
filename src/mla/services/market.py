"""Market intelligence groundwork: reference URLs and dated, sourced observations.

Implemented now: registering reference listings and recording observations by hand (price, title, ...),
plus a price comparison. Automatic collection is a contract only (`ReferenceCollector`): a future
collector (official API first; Scrapling only where the platform's terms and the law allow) must declare
that its terms were reviewed, is run one reference at a time on the user's request, and every value it
returns is stored as an external observation with its source and date, never as catalog data.
No scraping dependency is installed and nothing is collected automatically in this version.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from statistics import median
from typing import Protocol
from urllib.parse import urlsplit

from mla.persistence.db import Database, now_iso

log = logging.getLogger(__name__)
KINDS = ("price", "title", "description", "question", "review", "rating", "other")


class MarketError(ValueError):
    pass


@dataclass
class Reference:
    url: str
    product_id: int | None = None
    marketplace: str = ""
    title: str = ""
    notes: str = ""
    id: int | None = None
    created_at: str = ""


@dataclass
class Observation:
    kind: str
    value_text: str = ""
    value_cents: int | None = None
    source: str = "manual"  # manual | official_api | collector
    collector: str = ""
    collected_at: str = ""
    notes: str = ""
    reference_id: int | None = None
    id: int | None = None


@dataclass
class PriceComparison:
    our_price_cents: int | None
    observed: list[int] = field(default_factory=list)
    oldest: str = ""  # collection date of the oldest observation used

    @property
    def lowest(self) -> int | None:
        return min(self.observed) if self.observed else None

    @property
    def median(self) -> int | None:
        return int(median(self.observed)) if self.observed else None


class ReferenceCollector(Protocol):
    """Contract for future automatic collectors (not implemented in this version)."""
    name: str
    source: str            # "official_api" or "collector"
    terms_reviewed: bool   # the platform's terms allow this collection (declared by whoever enables it)

    def collect(self, reference: Reference) -> list[Observation]: ...


class MarketService:
    def __init__(self, db: Database):
        self.db = db

    def add_reference(self, ref: Reference) -> Reference:
        parts = urlsplit((ref.url or "").strip())
        if parts.scheme != "https" or not parts.hostname:
            raise MarketError("Use um endereço HTTPS completo do anúncio de referência.")
        ref.url = parts.geturl()
        ref.created_at = now_iso()
        try:
            cur = self.db.execute(
                "INSERT INTO market_references (product_id, marketplace, url, title, notes, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)", (ref.product_id, ref.marketplace, ref.url, ref.title, ref.notes,
                                               ref.created_at))
        except Exception as exc:
            if "UNIQUE" in str(exc).upper():
                raise MarketError("Essa referência já está cadastrada para o produto.") from exc
            raise
        ref.id = cur.lastrowid
        return ref

    def references(self, product_id: int) -> list[Reference]:
        return [Reference(url=r["url"], product_id=r["product_id"], marketplace=r["marketplace"], title=r["title"],
                          notes=r["notes"], id=r["id"], created_at=r["created_at"])
                for r in self.db.query("SELECT * FROM market_references WHERE product_id = ? ORDER BY id",
                                       (product_id,))]

    def record(self, reference_id: int, obs: Observation) -> Observation:
        if obs.kind not in KINDS:
            raise MarketError(f"Tipo de observação desconhecido: {obs.kind}")
        if obs.source not in ("manual", "official_api", "collector"):
            raise MarketError("Informe a origem da observação.")
        if obs.kind == "price" and (obs.value_cents is None or obs.value_cents <= 0):
            raise MarketError("Preço observado precisa ser maior que zero.")
        obs.reference_id = reference_id
        obs.collected_at = obs.collected_at or now_iso()
        cur = self.db.execute(
            "INSERT INTO market_observations (reference_id, kind, value_text, value_cents, source, collector,"
            " collected_at, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (reference_id, obs.kind, obs.value_text, obs.value_cents, obs.source, obs.collector, obs.collected_at,
             obs.notes))
        obs.id = cur.lastrowid
        return obs

    def collect_with(self, collector: ReferenceCollector, reference: Reference) -> list[Observation]:
        """Run a collector on ONE reference, on the user's request. Refused unless its terms were reviewed."""
        if not getattr(collector, "terms_reviewed", False):
            raise MarketError(f"O coletor {collector.name} não declarou que os termos da plataforma permitem esta "
                              "coleta; nada foi coletado.")
        if collector.source not in ("official_api", "collector"):
            raise MarketError("Coletor com origem inválida.")
        stored = []
        for obs in collector.collect(reference):
            obs.source, obs.collector = collector.source, collector.name
            obs.collected_at = now_iso()
            stored.append(self.record(reference.id, obs))  # type: ignore[arg-type]
        log.info("coleta %s em %s: %s observação(ões)", collector.name, reference.url, len(stored))
        return stored

    def price_comparison(self, product_id: int, our_price_cents: int | None) -> PriceComparison:
        """Latest observed price per reference of the product."""
        rows = self.db.query(
            "SELECT o.value_cents, o.collected_at FROM market_observations o"
            " JOIN market_references r ON r.id = o.reference_id"
            " WHERE r.product_id = ? AND o.kind = 'price' AND o.collected_at = ("
            "   SELECT MAX(o2.collected_at) FROM market_observations o2"
            "   WHERE o2.reference_id = o.reference_id AND o2.kind = 'price')", (product_id,))
        prices = [r["value_cents"] for r in rows if r["value_cents"]]
        oldest = min((r["collected_at"] for r in rows), default="")
        return PriceComparison(our_price_cents, prices, oldest)
