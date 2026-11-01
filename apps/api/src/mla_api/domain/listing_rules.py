"""Validation Engine and Attribute Mapper rules for Mercado Livre bulk listing.

Every issue carries its *source* so the UI never mixes them up:
- "interna": MLA's own catalog rules;
- "documentacao": rule confirmed by the official help pages (ref = PDF + page, docs/MLA_MERCADOLIVRE_RESEARCH.md);
- "template": rule read from the user's official workbook (e.g. a column marked "Obrigatório");
- "hipotese": inferred, shown as advice only (never an error).
Passing these checks does not mean Mercado Livre will accept the sheet; its own validation happens on upload.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date
from urllib.parse import urlparse

from mla_api.domain.catalog import gtin_valid
from mla_api.domain.template_inspector import norm

DAILY_LISTING_LIMIT = 10_000          # P1 p.8
PHOTO_GROUP_LIMIT = 10                # P3 p.2 (Gestor de fotos group), not a catalog limit
PHOTO_SEPARATOR = ","                 # P3 p.4 (capture: URLs separated by comma, no space)
OFFICIAL_PHOTO_HOST = "mlstatic.com"  # host of the Gestor URLs in P3 p.4


@dataclass(frozen=True)
class Issue:
    code: str
    severity: str  # error | warning | info
    source: str    # interna | documentacao | template | hipotese
    message: str
    fix: str
    field: str = ""
    ref: str = ""
    sku: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


# --- inputs (plain data so the engine is testable without a database) ------------------------------------------
@dataclass
class VariantData:
    sku: str
    attributes: dict[str, str]
    gtin: str = ""
    price_cents: int | None = None
    stock: int = 0


@dataclass
class ProductData:
    id: str
    sku: str
    name: str
    brand: str = ""
    model: str = ""
    gtin: str = ""
    description: str = ""
    price_cents: int | None = None
    stock: int = 0
    attributes: dict[str, str] = field(default_factory=dict)
    variants: list[VariantData] = field(default_factory=list)
    photo_urls: list[str] = field(default_factory=list)   # official URLs, in order
    photos_without_url: int = 0                            # stored images that still lack an official URL
    catalog_code: str = ""


@dataclass
class TemplateContext:
    deadline: date | None = None
    deadline_confirmed: bool = False
    columns: list[dict] = field(default_factory=list)      # [{col, header, required}] confirmed by the user
    rules: dict[str, dict] = field(default_factory=dict)   # {col: {source, default}}


# --- photos ------------------------------------------------------------------------------------------------------
def photo_url_problem(url: str) -> Issue | None:
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or not parsed.netloc or " " in url.strip():
        return Issue("photo_url_invalid", "error", "interna", f"URL de foto inválida: {url[:80]}",
                     "Cole a URL completa copiada do Gestor de fotos (começa com https://).", "fotos")
    if PHOTO_SEPARATOR in url:
        return Issue("photo_url_invalid", "error", "interna", "Uma URL de foto contém vírgula.",
                     "Registre uma URL por foto; o MLA junta as URLs com vírgula na exportação.", "fotos")
    host = parsed.hostname or ""
    if not (host == OFFICIAL_PHOTO_HOST or host.endswith("." + OFFICIAL_PHOTO_HOST)):
        return Issue("photo_url_external", "warning", "hipotese",
                     f"URL fora do Gestor de fotos ({host}). Não está confirmado que o Mercado Livre aceita.",
                     "Prefira as URLs geradas pelo Gestor de fotos.", "fotos", "P3 p.1–4; pesquisa G10")
    return None


def photo_cell(urls: list[str]) -> str:
    """Value for the "Fotos" column: URLs in order, comma-separated without spaces (P3 p.4)."""
    return PHOTO_SEPARATOR.join(u.strip() for u in urls if u.strip())


# --- validation --------------------------------------------------------------------------------------------------
def validate_product(p: ProductData) -> list[Issue]:
    out: list[Issue] = []
    add = out.append
    if not p.name.strip():
        add(Issue("name_missing", "error", "interna", "Produto sem nome.", "Preencha o nome.", "name"))
    if p.price_cents is None or p.price_cents <= 0:
        add(Issue("price_missing", "error", "interna", "Preço de venda não informado.",
                  "Informe o preço de venda.", "price_cents"))
    if p.stock <= 0 and not p.variants:
        add(Issue("stock_zero", "warning", "interna", "Estoque zerado.", "Confirme o estoque disponível.", "stock"))
    if p.gtin and not gtin_valid(p.gtin):
        add(Issue("gtin_invalid", "warning", "interna", f"GTIN/EAN {p.gtin} com dígito verificador inválido.",
                  "Confira o código de barras.", "gtin"))
    if not p.brand.strip() and not p.catalog_code:
        add(Issue("brand_missing", "warning", "interna", "Marca não informada.",
                  "Informe a marca (o Resumo de erros oficial cita Marca como exemplo de dado faltante).",
                  "brand", "P2 p.5"))

    # Photos (P1 p.6, P3).
    if not p.photo_urls:
        sev, fix = ("info", "Com código de catálogo, a planilha pode trazer as fotos (P1 p.6).") if p.catalog_code \
            else ("warning", "Gere as URLs no Gestor de fotos e registre-as na Central de Fotos.")
        add(Issue("photos_missing", sev, "documentacao", "Nenhuma URL oficial de foto registrada.", fix, "fotos",
                  "P1 p.6; P3 p.1–4"))
    if p.photos_without_url:
        add(Issue("photos_without_url", "info", "interna",
                  f"{p.photos_without_url} foto(s) do catálogo ainda sem URL do Gestor de fotos.",
                  "Envie essas fotos ao Gestor de fotos e cole as URLs geradas.", "fotos", "P3 p.2–3"))
    if len(p.photo_urls) > PHOTO_GROUP_LIMIT:
        add(Issue("photos_over_group_limit", "warning", "documentacao",
                  f"{len(p.photo_urls)} URLs; o Gestor de fotos aceita até {PHOTO_GROUP_LIMIT} por grupo.",
                  "Confira no template quantas fotos a coluna aceita.", "fotos", "P3 p.2"))
    for url in p.photo_urls:
        if issue := photo_url_problem(url):
            add(issue)

    # Catalog profile (P2 p.2-4).
    if p.catalog_code:
        add(Issue("catalog_profile", "info", "documentacao",
                  "Produto com Código de catálogo ML: colunas marcadas no template como dispensáveis para catálogo "
                  "podem ficar vazias.", "Revise os dados que o Mercado Livre preencher.", "catalog_code",
                  "P2 p.2–3"))

    # Variations = duplicated rows (P1 p.6); grouping rule pending a real template.
    seen: dict[tuple, str] = {}
    keys = None
    for v in p.variants:
        if not v.attributes:
            add(Issue("variant_no_attributes", "error", "interna", f"Variação {v.sku} sem atributos (ex.: Cor).",
                      "Informe o que diferencia a variação.", "variants", sku=v.sku))
            continue
        combo = tuple(sorted((norm(k), norm(val)) for k, val in v.attributes.items()))
        if combo in seen:
            add(Issue("variant_duplicate", "error", "interna",
                      f"Variações {seen[combo]} e {v.sku} têm os mesmos atributos.", "Diferencie ou remova uma.",
                      "variants", sku=v.sku))
        seen[combo] = v.sku
        names = {norm(k) for k in v.attributes}
        if keys is None:
            keys = names
        elif names != keys:
            add(Issue("variant_inconsistent", "warning", "interna",
                      f"Variação {v.sku} usa atributos diferentes das demais.",
                      "Use os mesmos tipos de atributo em todas as variações.", "variants", sku=v.sku))
        if v.gtin and not gtin_valid(v.gtin):
            add(Issue("variant_gtin_invalid", "warning", "interna", f"GTIN da variação {v.sku} inválido.",
                      "Confira o código de barras.", "variants", sku=v.sku))
    return [i if i.sku else Issue(**{**i.as_dict(), "sku": p.sku}) for i in out]


def validate_template(t: TemplateContext | None, today: date) -> list[Issue]:
    if t is None:
        return [Issue("template_missing", "error", "documentacao", "Nenhum template oficial selecionado.",
                      "Baixe a planilha no Anunciador em massa da conta e envie-a em Templates.", "template",
                      "P1 p.5, p.8")]
    out = []
    if t.deadline and t.deadline < today:
        out.append(Issue("template_expired", "error", "documentacao",
                         f"A data limite de envio desta planilha ({t.deadline:%d/%m/%Y}) já passou.",
                         "Baixe uma nova planilha no Anunciador em massa.", "template", "P2 p.1"))
    elif t.deadline and not t.deadline_confirmed:
        out.append(Issue("template_deadline_unconfirmed", "warning", "template",
                         f"Data limite interpretada como {t.deadline:%d/%m/%Y} (ano deduzido).",
                         "Confirme a data na tela do template.", "template", "P2 p.2"))
    elif t.deadline is None:
        out.append(Issue("template_deadline_unknown", "warning", "template",
                         "Data limite de envio não encontrada no arquivo.",
                         "Confira a aba Ajuda e informe a data manualmente.", "template", "P2 p.1"))
    if not t.columns:
        out.append(Issue("mapping_missing", "error", "interna", "Colunas da aba ainda não confirmadas.",
                         "Confirme a linha de cabeçalho e o mapeamento da aba.", "mapping"))
    for col in t.columns:
        rule = t.rules.get(col["col"]) or {}
        if col.get("required") and not rule.get("source") and not str(rule.get("default", "")).strip():
            out.append(Issue("required_unmapped", "error", "template",
                             f'Coluna obrigatória "{col["header"]}" ({col["col"]}) sem mapeamento.',
                             "Associe um campo do catálogo ou um valor padrão.", "mapping", "P2 p.4"))
    return out


def batch_size_issue(rows: int) -> Issue | None:
    if rows > DAILY_LISTING_LIMIT:
        return Issue("batch_over_daily_limit", "error", "documentacao",
                     f"{rows} linhas; o limite é de {DAILY_LISTING_LIMIT} anúncios criados por dia.",
                     "Divida o lote.", "batch", "P1 p.8")
    return None


def sheet_rows(p: ProductData) -> int:
    """One row per variation (P1 p.6), otherwise one row per product (P1 p.6: each row becomes a listing)."""
    return max(1, len(p.variants))


# --- attribute mapper --------------------------------------------------------------------------------------------
SOURCE_FIELDS: dict[str, str] = {
    "sku": "SKU (variação, se houver)",
    "name": "Nome / título",
    "brand": "Marca",
    "model": "Modelo",
    "gtin": "Código universal (GTIN/EAN)",
    "description": "Descrição",
    "price": "Preço de venda",
    "stock": "Estoque",
    "photos": "Fotos (URLs oficiais)",
    "catalog_code": "Código de catálogo ML",
}

# Suggestions only (always confirmed by the user). Header texts are not confirmed until a real template is seen.
_SYNONYMS: list[tuple[str, tuple[str, ...]]] = [
    ("catalog_code", ("codigo de catalogo ml", "codigo do catalogo ml")),
    ("photos", ("fotos", "imagens")),
    ("gtin", ("codigo universal", "gtin", "ean", "codigo de barras")),
    ("sku", ("sku",)),
    ("price", ("preco",)),
    ("stock", ("estoque", "quantidade")),
    ("brand", ("marca",)),
    ("model", ("modelo",)),
    ("description", ("descricao",)),
    ("name", ("titulo", "nome do produto")),
]


def suggest_source(header: str) -> str | None:
    text = norm(header)
    for source, needles in _SYNONYMS:
        if any(re.search(rf"\b{re.escape(n)}\b", text) for n in needles):
            return source
    return None


def resolve(source: str, p: ProductData, v: VariantData | None) -> str:
    if source.startswith("attr:"):
        key = source[5:]
        return (v.attributes.get(key) if v else None) or p.attributes.get(key, "")
    if source == "sku":
        return v.sku if v else p.sku
    if source == "gtin":
        return (v.gtin if v and v.gtin else p.gtin)
    if source == "price":
        cents = v.price_cents if v and v.price_cents is not None else p.price_cents
        return "" if cents is None else f"{cents / 100:.2f}"
    if source == "stock":
        return str(v.stock if v else p.stock)
    if source == "photos":
        return photo_cell(p.photo_urls)
    if source == "catalog_code":
        return p.catalog_code
    return str(getattr(p, source, "") or "")


def preview_rows(products: list[ProductData], t: TemplateContext) -> list[dict]:
    """What would be written in the data rows (no file is touched). One row per variation (P1 p.6)."""
    rows = []
    for p in products:
        for v in (p.variants or [None]):
            values = {}
            for col in t.columns:
                rule = t.rules.get(col["col"]) or {}
                value = resolve(rule["source"], p, v) if rule.get("source") else ""
                values[col["col"]] = value or str(rule.get("default", "") or "")
            rows.append({"product_id": p.id, "sku": v.sku if v else p.sku, "values": values})
    return rows
