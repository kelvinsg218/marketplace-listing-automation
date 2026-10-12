"""Product validation.

Errors block automation; warnings are shown but do not block.

Marketplace limits live in MARKETPLACE_RULES. Each entry says whether it was
confirmed against the live marketplace form. Unconfirmed values are
conservative and must be re-checked in the marketplace integration phases
(see docs/DECISIONS.md). Category-specific required attributes are NOT
hard-coded: they come from the marketplace form at automation time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from mla.core.enums import CatalogStatus, Marketplace
from mla.core.models import Product

Severity = Literal["error", "warning"]
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MIN_IMAGE_SIDE_PX = 500


@dataclass(frozen=True)
class MarketplaceRules:
    max_title: int | None
    max_images: int | None
    confirmed: bool  # verified against the real seller form?


MARKETPLACE_RULES: dict[Marketplace, MarketplaceRules] = {
    Marketplace.MERCADO_LIVRE: MarketplaceRules(max_title=60, max_images=None, confirmed=False),
    Marketplace.SHOPEE: MarketplaceRules(max_title=120, max_images=9, confirmed=False),
    Marketplace.SIMULATED: MarketplaceRules(max_title=60, max_images=10, confirmed=True),
}


@dataclass(frozen=True)
class Issue:
    field: str
    message: str
    severity: Severity = "error"
    marketplace: Marketplace | None = None


@dataclass
class ValidationReport:
    issues: list[Issue] = field(default_factory=list)

    def add(self, field_name: str, message: str, severity: Severity = "error",
            marketplace: Marketplace | None = None) -> None:
        self.issues.append(Issue(field_name, message, severity, marketplace))

    def errors(self, marketplace: Marketplace | None = None) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"
                and (i.marketplace is None or i.marketplace == marketplace)]

    def warnings(self, marketplace: Marketplace | None = None) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"
                and (i.marketplace is None or marketplace is None or i.marketplace == marketplace)]

    def catalog_errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error" and i.marketplace is None]

    def ready_for(self, marketplace: Marketplace) -> bool:
        return not self.errors(marketplace)

    def for_field(self, field_name: str) -> list[Issue]:
        return [i for i in self.issues if i.field == field_name]


def validate_identity(product: Product) -> list[str]:
    """Minimum needed to save a record at all."""
    problems = []
    if not product.internal_name.strip():
        problems.append("Informe o nome interno do produto.")
    if not product.sku.strip():
        problems.append("Informe o SKU do produto.")
    elif any(ch.isspace() for ch in product.sku.strip()):
        problems.append("O SKU não pode conter espaços.")
    return problems


def validate_product(product: Product) -> ValidationReport:
    report = ValidationReport()
    for message in validate_identity(product):
        report.add("sku" if "SKU" in message else "internal_name", message)

    if not product.title.strip():
        report.add("title", "Escreva o título do anúncio.")
    if not product.category.strip():
        report.add("category", "Escolha a categoria do produto.")
    if not product.description.strip():
        report.add("description", "Escreva a descrição do produto.")
    elif len(product.description.strip()) < 30:
        report.add("description", "A descrição está muito curta; detalhe o produto para o comprador.", "warning")
    if not product.brand.strip():
        report.add("brand", "Marca não informada; muitas categorias exigem esse dado.", "warning")

    if product.price_cents is None:
        report.add("price", "Informe o preço de venda.")
    elif product.price_cents <= 0:
        report.add("price", "O preço precisa ser maior que zero.")
    if product.stock <= 0 and not product.variants:
        report.add("stock", "Estoque zerado: o anúncio não pode ser publicado sem estoque.")
    if product.variants:
        if sum(v.stock for v in product.variants) <= 0:
            report.add("variants", "Todas as variações estão sem estoque.")
        names = [v.name.strip().lower() for v in product.variants]
        if any(not n for n in names):
            report.add("variants", "Toda variação precisa de um nome (ex.: Cor: Azul).")
        if len(set(names)) != len(names):
            report.add("variants", "Há variações com o mesmo nome.")
        skus = [v.sku.strip().lower() for v in product.variants if v.sku]
        if len(set(skus)) != len(skus) or product.sku.strip().lower() in skus:
            report.add("variants", "Os SKUs das variações precisam ser únicos.")

    if not product.images:
        report.add("images", "Adicione pelo menos uma imagem.")
    for image in product.images:
        ext = "." + image.filename.rsplit(".", 1)[-1].lower() if "." in image.filename else ""
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            report.add("images", f"Formato de imagem não aceito: {image.filename} (use JPG, PNG ou WEBP).")
        if image.size_bytes > MAX_IMAGE_BYTES:
            report.add("images", f"Imagem acima de 10 MB: {image.filename}.")
        if image.width and image.height and min(image.width, image.height) < MIN_IMAGE_SIDE_PX:
            report.add("images", f"Imagem pequena ({image.width}×{image.height} px); use pelo menos "
                                 f"{MIN_IMAGE_SIDE_PX} px no menor lado.", "warning")

    if product.weight_g is None or product.weight_g <= 0:
        report.add("weight", "Informe o peso com embalagem.")
    dims = (product.length_mm, product.width_mm, product.height_mm)
    if any(d is None or d <= 0 for d in dims):
        report.add("dimensions", "Informe comprimento, largura e altura da embalagem.")

    for marketplace in product.enabled_marketplaces():
        rules = MARKETPLACE_RULES.get(marketplace)
        if rules is None:
            continue
        title = product.title.strip()
        if rules.max_title and len(title) > rules.max_title:
            report.add("title", f"Título com {len(title)} caracteres; o limite no {marketplace.label} "
                                f"é {rules.max_title}.", "error", marketplace)
        if rules.max_images and len(product.images) > rules.max_images:
            report.add("images", f"O {marketplace.label} usa no máximo {rules.max_images} imagens; "
                                 f"as demais serão ignoradas.", "warning", marketplace)
        price = product.price_for(marketplace)
        if price is not None and price <= 0:
            report.add("price", f"Preço inválido para o {marketplace.label}.", "error", marketplace)
    return report


def derive_status(product: Product, report: ValidationReport | None = None) -> CatalogStatus:
    report = report or validate_product(product)
    if not report.catalog_errors():
        return CatalogStatus.READY
    has_content = bool(product.title.strip() or product.price_cents or product.images or product.description.strip())
    return CatalogStatus.INCOMPLETE if has_content else CatalogStatus.DRAFT
