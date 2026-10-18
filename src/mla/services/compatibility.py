"""Product compatibility rules.

Compatibilities are never inferred: each one is entered or imported with its
source. Client data defaults to confirmed; anything else starts unverified and
is shown as such until the user confirms it.
"""
from __future__ import annotations

import logging
import re

from mla.core.enums import DataSource, Verification
from mla.core.models import Compatibility
from mla.persistence.compatibility import CompatibilityRepository, DuplicateCompatibilityError

log = logging.getLogger(__name__)
_YEAR_RE = re.compile(r"(?<!\d)(19\d{2}|20\d{2}|2100)(?!\d)")
_OPEN_END = re.compile(r"(\+|em diante|ou superior|acima|a partir)", re.IGNORECASE)
_UNTIL = re.compile(r"^\s*(at[eé]|ate)\b", re.IGNORECASE)


class CompatibilityError(ValueError):
    pass


def default_verification(source: DataSource) -> Verification:
    return Verification.CONFIRMED if source is DataSource.CLIENT else Verification.UNVERIFIED


def parse_year(text: str) -> int | None:
    text = (text or "").strip()
    if not text:
        return None
    match = _YEAR_RE.fullmatch(text.split(".")[0].strip())  # XLSX numbers arrive as "2015.0"
    if not match:
        raise CompatibilityError(f"Ano inválido: {text!r} (use 4 dígitos, ex.: 2015).")
    return int(match.group(1))


def parse_years(text: str) -> tuple[int | None, int | None]:
    """'2010-2015' / '2010 a 2015' / '2012' / '2018+' / 'até 2014' -> (from, to)."""
    text = (text or "").strip()
    if not text:
        return None, None
    years = [int(y) for y in _YEAR_RE.findall(text)]
    if not years or len(years) > 2:
        raise CompatibilityError(f"Não foi possível ler os anos em {text!r} (ex.: 2010-2015).")
    if len(years) == 2:
        return years[0], years[1]
    if _UNTIL.search(text):
        return None, years[0]
    if _OPEN_END.search(text):
        return years[0], None
    return years[0], years[0]


class CompatibilityService:
    def __init__(self, repo: CompatibilityRepository):
        self.repo = repo

    def validate(self, c: Compatibility) -> None:
        c.brand, c.model, c.version = c.brand.strip(), c.model.strip(), c.version.strip()
        c.reference_code, c.notes, c.source_detail = c.reference_code.strip(), c.notes.strip(), c.source_detail.strip()
        if c.product_id is None:
            raise CompatibilityError("Escolha o produto.")
        if not c.model:
            raise CompatibilityError("Informe o modelo compatível.")
        for year in (c.year_from, c.year_to):
            if year is not None and not 1900 <= year <= 2100:
                raise CompatibilityError(f"Ano fora do intervalo aceito: {year}.")
        if c.year_from and c.year_to and c.year_from > c.year_to:
            raise CompatibilityError("O ano inicial precisa ser menor ou igual ao ano final.")

    def save(self, c: Compatibility) -> Compatibility:
        self.validate(c)
        try:
            self.repo.save(c)
        except DuplicateCompatibilityError as exc:
            raise CompatibilityError(str(exc)) from exc
        return c

    def replace_for_product(self, product_id: int, items: list[Compatibility]) -> None:
        """Make the product's list equal to `items` (ids kept for existing rows)."""
        for item in items:
            item.product_id = product_id
            self.validate(item)
        keep = {i.id for i in items if i.id is not None}
        stale = [c.id for c in self.repo.list_for_product(product_id) if c.id not in keep]
        with self.repo.db.transaction():
            self.repo.delete(stale)
            for item in items:
                try:
                    self.repo.save(item)
                except DuplicateCompatibilityError as exc:
                    raise CompatibilityError(f"{item.brand} {item.model}: {exc}") from exc

    def list_for_product(self, product_id: int) -> list[Compatibility]:
        return self.repo.list_for_product(product_id)

    def search(self, text: str = "", verification: Verification | None = None, source: DataSource | None = None,
               limit: int = 500, offset: int = 0) -> list[Compatibility]:
        return self.repo.search(text, verification, source, limit=limit, offset=offset)

    def count(self, text: str = "", verification: Verification | None = None,
              source: DataSource | None = None) -> int:
        return self.repo.count(text, verification, source)

    def set_verification(self, ids: list[int], verification: Verification) -> int:
        changed = self.repo.set_verification(ids, verification)
        log.info("compatibilidades marcadas como %s: %s", verification, changed)
        return changed

    def delete(self, ids: list[int]) -> int:
        return self.repo.delete(ids)
