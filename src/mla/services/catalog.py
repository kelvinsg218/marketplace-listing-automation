from __future__ import annotations

import copy
import logging
import re
from collections.abc import Callable

from mla.core.models import Product, ProductSummary
from mla.core.validation import (
    CategoryRule, ValidationReport, derive_status, normalize_gtin, validate_identity, validate_product,
)
from mla.persistence.repositories import ProductQuery, ProductRepository
from mla.services.files import FileStore
from mla.services.images import ImageStore

log = logging.getLogger(__name__)


class CatalogError(ValueError):
    pass


class CatalogService:
    def __init__(self, products: ProductRepository, images: ImageStore, files: FileStore | None = None,
                 rules: Callable[[], list[CategoryRule]] | None = None,
                 confirmed_compat: Callable[[int], int] | None = None):
        self.products = products
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

    def save(self, product: Product) -> ValidationReport:
        """Create or update. Only identity problems block saving; the rest sets the status."""
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
        if product.id is None:
            self.products.insert(product)
            log.info("produto criado id=%s sku=%s status=%s", product.id, product.sku, product.status)
        else:
            self.products.update(product)
            log.info("produto atualizado id=%s status=%s", product.id, product.status)
        for hook in self.after_save:
            hook(product.id)
        return report

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
        self.save(clone)
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
