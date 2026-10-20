from __future__ import annotations

import copy
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass

from mla.core.changes import FieldChange, diff_products
from mla.core.enums import CommercialStatus, Condition
from mla.core.models import Product, ProductSummary
from mla.core.validation import (
    CategoryRule, ValidationReport, derive_status, normalize_gtin, validate_identity, validate_product,
)
from mla.persistence.changes import ChangeRepository
from mla.persistence.repositories import ProductQuery, ProductRepository
from mla.services.files import FileStore
from mla.services.images import ImageStore

log = logging.getLogger(__name__)

MANUAL_EDIT = "Edição manual"
BULK_EDIT = "Edição em lote"

# Descriptive fields only. Price, stock, GTIN and SKU are never changed in bulk: they come from the client's base
# and a wrong bulk value would reach every listing.
BULK_FIELDS: dict[str, str] = {
    "category": "Categoria", "subcategory": "Subcategoria", "brand": "Marca", "supplier": "Fornecedor",
    "unit": "Unidade de medida", "warranty": "Garantia", "condition": "Condição",
    "commercial_status": "Status comercial",
}
BULK_LIMIT = 5000


@dataclass
class BulkChange:
    product_id: int
    sku: str
    name: str
    label: str
    old: str
    new: str


class CatalogError(ValueError):
    pass


class CatalogService:
    def __init__(self, products: ProductRepository, images: ImageStore, files: FileStore | None = None,
                 rules: Callable[[], list[CategoryRule]] | None = None,
                 confirmed_compat: Callable[[int], int] | None = None, changes: ChangeRepository | None = None):
        self.products = products
        self.changes = changes  # field-level history (None = not recorded, e.g. in isolated tests)
        self.images = images
        self.files = files
        self._rules = rules or (lambda: [])
        self._confirmed_compat = confirmed_compat
        self.after_save: list[Callable[[int], None]] = []  # e.g. re-derive listings of the product

    def validate(self, product: Product) -> ValidationReport:
        rules = self._rules()
        compat = None
        if any(r.requires_compatibility and r.matches(product.category) for r in rules):
            compat = self._confirmed_compat(product.id) if (self._confirmed_compat and product.id) else 0
        return validate_product(product, rules, compat)

    def save(self, product: Product, source: str = MANUAL_EDIT) -> ValidationReport:
        """Create or update. Only identity problems block saving; the rest sets the status.

        `source` names the origin of the change in the history ("Edição manual", "Importação #3", ...)."""
        product.internal_name = product.internal_name.strip()
        product.sku = product.sku.strip()
        product.title = product.title.strip()
        product.gtin = normalize_gtin(product.gtin)
        problems = validate_identity(product)
        if problems:
            raise CatalogError(" ".join(problems))
        for sku in [product.sku, *(v.sku.strip() for v in product.variants if v.sku and v.sku.strip())]:
            if self.products.sku_exists(sku, product.id):
                raise CatalogError(f"Já existe um produto ou variação com o SKU '{sku}'.")
        report = self.validate(product)
        product.status = derive_status(product, report)
        with self.products.db.transaction():
            if product.id is None:
                self.products.insert(product)
                log.info("produto criado id=%s sku=%s status=%s", product.id, product.sku, product.status)
                if self.changes is not None:
                    self.changes.add(product.id, product.sku, [FieldChange("_created", "Produto criado", "",
                                                                           product.sku)], source)
            else:
                old = self.products.get(product.id) if self.changes is not None else None
                self.products.update(product)
                log.info("produto atualizado id=%s status=%s", product.id, product.status)
                if old is not None:
                    self.changes.add(product.id, product.sku, diff_products(old, product), source)
        for hook in self.after_save:
            hook(product.id)
        return report

    # ------------------------------------------------------------------ bulk edit
    @staticmethod
    def _bulk_values(values: dict[str, object]) -> dict[str, object]:
        if not values:
            raise CatalogError("Escolha ao menos um campo para alterar.")
        clean: dict[str, object] = {}
        for name, value in values.items():
            if name not in BULK_FIELDS:
                raise CatalogError(f"O campo {name!r} não pode ser alterado em lote.")
            if name == "condition":
                clean[name] = Condition(value)
            elif name == "commercial_status":
                clean[name] = CommercialStatus(value)
            else:
                text = " ".join(str(value or "").split())
                if not text:
                    raise CatalogError(f"Informe o novo valor de {BULK_FIELDS[name]} (para apagar um campo, edite "
                                       "o produto).")
                clean[name] = text
        return clean

    def bulk_preview(self, product_ids: list[int], values: dict[str, object]) -> list[BulkChange]:
        """What `bulk_update` would change, product by product (nothing is written)."""
        clean = self._bulk_values(values)
        if len(product_ids) > BULK_LIMIT:
            raise CatalogError(f"Selecione no máximo {BULK_LIMIT} produtos por edição em lote.")
        rows: list[BulkChange] = []
        for pid in product_ids:
            product = self.products.get(pid)
            if product is None:
                continue
            for name, value in clean.items():
                current = getattr(product, name)
                if current != value:
                    show = (lambda v: v.label) if name in ("condition", "commercial_status") else str
                    rows.append(BulkChange(pid, product.sku, product.internal_name, BULK_FIELDS[name],
                                           show(current) if current not in (None, "") else "", show(value)))
        return rows

    def bulk_update(self, product_ids: list[int], values: dict[str, object]) -> int:
        """Apply the same descriptive values to many products, all or nothing. Returns products changed."""
        clean = self._bulk_values(values)
        if len(product_ids) > BULK_LIMIT:
            raise CatalogError(f"Selecione no máximo {BULK_LIMIT} produtos por edição em lote.")
        changed = 0
        with self.products.db.transaction():
            for pid in product_ids:
                product = self.products.get(pid)
                if product is None:
                    continue
                if all(getattr(product, name) == value for name, value in clean.items()):
                    continue
                for name, value in clean.items():
                    setattr(product, name, value)
                try:
                    self.save(product, source=BULK_EDIT)
                except CatalogError as exc:
                    raise CatalogError(f"{product.sku}: {exc} Nenhum produto foi alterado.") from exc
                changed += 1
        log.info("edição em lote: %s produto(s) alterado(s), campos=%s", changed, sorted(clean))
        return changed

    def history(self, product_id: int, limit: int = 500):
        return self.changes.for_product(product_id, limit) if self.changes is not None else []

    def get(self, product_id: int) -> Product | None:
        return self.products.get(product_id)

    def search(self, query: ProductQuery | None = None) -> list[ProductSummary]:
        return self.products.list_summaries(query)

    def delete(self, product_ids: list[int]) -> int:
        count = self.products.delete(product_ids)
        self.images.remove_orphans(self.products.image_files_in_use())
        if self.files is not None:
            self.files.remove_orphans(self.products.technical_files_in_use())
        log.info("produtos excluídos: %s", count)
        return count

    def next_free_sku(self, base: str) -> str:
        stem = re.sub(r"-COPIA(-\d+)?$", "", base, flags=re.IGNORECASE)
        candidate = f"{stem}-COPIA"
        n = 2
        while self.products.sku_exists(candidate):
            candidate = f"{stem}-COPIA-{n}"
            n += 1
        return candidate

    def duplicate(self, product_id: int) -> Product:
        original = self.products.get(product_id)
        if original is None:
            raise CatalogError("Produto não encontrado.")
        clone = copy.deepcopy(original)
        clone.id = None
        clone.sku = self.next_free_sku(original.sku)
        clone.internal_name = f"{original.internal_name} (cópia)"
        for image in clone.images:
            image.id = None
        for variant in clone.variants:
            variant.id = None
            variant.sku = None  # variant SKUs are unique; the user must set new ones
        self.save(clone, source=f"Duplicado de {original.sku}")
        return clone

    def revalidate_all(self) -> int:
        """Recompute stored statuses (e.g. after validation rules change)."""
        changed = 0
        for pid in self.products.all_ids():
            product = self.products.get(pid)
            if product is None:
                continue
            status = derive_status(product, self.validate(product))
            if status != product.status:
                self.products.set_status(pid, status)
                changed += 1
        return changed
