"""Target fields and automatic column recognition.

Recognition is a deterministic dictionary of normalised column names (no AI).
"exact" names are applied directly; "probable" ones (e.g. `codigo` → SKU) are
applied but flagged so the user confirms them before planning.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from statistics import mean

TARGETS = ("products", "compatibility")
IGNORE = ""


def normalize_key(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(text or ""))
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]+", "_", plain).strip("_")


@dataclass(frozen=True)
class TargetField:
    key: str
    label: str
    group: str
    kind: str = "text"
    multi: bool = False  # several columns may map to it (each becomes one entry)


PRODUCT_FIELDS: tuple[TargetField, ...] = (
    TargetField("sku", "SKU", "Identificação", "sku"),
    TargetField("parent_sku", "SKU do produto pai (variação)", "Identificação", "sku"),
    TargetField("variant_name", "Nome da variação", "Identificação"),
    TargetField("internal_name", "Nome do produto", "Identificação"),
    TargetField("commercial_name", "Nome comercial", "Identificação"),
    TargetField("title", "Título do anúncio", "Identificação"),
    TargetField("manufacturer_code", "Código do fabricante", "Identificação"),
    TargetField("gtin", "GTIN/EAN", "Identificação", "gtin"),
    TargetField("brand", "Marca", "Identificação"),
    TargetField("model", "Modelo", "Identificação"),
    TargetField("category", "Categoria", "Identificação"),
    TargetField("subcategory", "Subcategoria", "Identificação"),
    TargetField("supplier", "Fornecedor", "Identificação"),
    TargetField("cost_cents", "Preço de custo", "Comercial", "money"),
    TargetField("price_cents", "Preço de venda", "Comercial", "money"),
    TargetField("promo_price_cents", "Preço promocional", "Comercial", "money"),
    TargetField("stock", "Estoque", "Comercial", "int"),
    TargetField("min_stock", "Estoque mínimo", "Comercial", "int"),
    TargetField("unit", "Unidade de medida", "Comercial"),
    TargetField("warranty", "Garantia", "Comercial"),
    TargetField("condition", "Condição", "Comercial", "condition"),
    TargetField("commercial_status", "Status comercial", "Comercial", "commercial_status"),
    TargetField("description", "Descrição", "Técnico", "longtext"),
    TargetField("technical_description", "Descrição técnica", "Técnico", "longtext"),
    TargetField("features", "Características", "Técnico", "longtext"),
    TargetField("material", "Material", "Técnico"),
    TargetField("color", "Cor", "Técnico"),
    TargetField("weight_kg", "Peso (kg)", "Técnico", "weight_kg"),
    TargetField("weight_g", "Peso (g)", "Técnico", "weight_g"),
    TargetField("length_cm", "Comprimento (cm)", "Técnico", "dim_cm"),
    TargetField("width_cm", "Largura (cm)", "Técnico", "dim_cm"),
    TargetField("height_cm", "Altura (cm)", "Técnico", "dim_cm"),
    TargetField("dimensions_cm", "Dimensões C×L×A (cm)", "Técnico", "dims"),
    TargetField("package_contents", "Conteúdo da embalagem", "Técnico", "longtext"),
    TargetField("package_type", "Tipo de embalagem", "Técnico"),
    TargetField("availability_days", "Prazo de disponibilidade (dias)", "Comercial", "int"),
    TargetField("shipping_notes", "Informações de envio", "Técnico", "longtext"),
    TargetField("original_description", "Descrição original", "Técnico", "longtext"),
    TargetField("manufacturer_refs", "Referências de fabricante", "Técnico"),
    TargetField("internal_notes", "Observações internas", "Técnico", "longtext"),
    TargetField("spec", "Especificação adicional (usa o nome da coluna)", "Técnico", "spec", multi=True),
    TargetField("attr", "Atributo personalizado (usa o nome da coluna)", "Técnico", "attr", multi=True),
    TargetField("images", "Imagens (arquivos ou links)", "Mídia", "media", multi=True),
    TargetField("files", "Arquivos técnicos (PDF, manual)", "Mídia", "files", multi=True),
)

COMPAT_FIELDS: tuple[TargetField, ...] = (
    TargetField("sku", "SKU do produto", "Compatibilidade", "sku"),
    TargetField("brand", "Marca compatível", "Compatibilidade"),
    TargetField("model", "Modelo compatível", "Compatibilidade"),
    TargetField("version", "Versão", "Compatibilidade"),
    TargetField("year_from", "Ano inicial", "Compatibilidade", "year"),
    TargetField("year_to", "Ano final", "Compatibilidade", "year"),
    TargetField("years", "Anos (ex.: 2010-2015)", "Compatibilidade", "years"),
    TargetField("reference_code", "Código de referência", "Compatibilidade"),
    TargetField("notes", "Observações", "Compatibilidade"),
    TargetField("source_detail", "Fonte da informação", "Compatibilidade"),
)


def fields_for(target: str) -> tuple[TargetField, ...]:
    return COMPAT_FIELDS if target == "compatibility" else PRODUCT_FIELDS


def field_by_key(target: str, key: str) -> TargetField | None:
    return next((f for f in fields_for(target) if f.key == key), None)


def _syn(exact: str = "", probable: str = "") -> dict[str, str]:
    table = {normalize_key(k): "exact" for k in exact.split(",") if k.strip()}
    table.update({normalize_key(k): "probable" for k in probable.split(",") if k.strip()})
    return table


PRODUCT_SYNONYMS: dict[str, dict[str, str]] = {
    "sku": _syn("sku,sku_principal,codigo_sku,sku_produto,cod_sku,sku_do_produto",
                "codigo,cod,cod_produto,codigo_produto,codigo_do_produto,referencia,ref,cod_interno,codigo_interno,"
                "id_produto,item,cod_item,codigo_item"),
    "parent_sku": _syn("sku_pai,codigo_pai,cod_pai,parent_sku,sku_parent,produto_pai,sku_principal_pai"),
    "variant_name": _syn("variacao,nome_variacao,variante,variation,descricao_variacao"),
    "internal_name": _syn("nome,nome_produto,produto,nome_interno,nome_do_produto,product_name,name",
                          "descricao_curta,desc_curta"),
    "commercial_name": _syn("nome_comercial,nome_fantasia_produto"),
    "title": _syn("titulo,titulo_anuncio,titulo_do_anuncio,title"),
    "manufacturer_code": _syn("codigo_fabricante,cod_fabricante,part_number,partnumber,mpn,codigo_do_fabricante",
                              "pn,ref_fabricante,referencia_fabricante"),
    "gtin": _syn("ean,gtin,ean13,ean_13,gtin_ean,ean_gtin,codigo_barras,cod_barras,codigo_de_barras,upc,gtin13"),
    "brand": _syn("marca,brand", "fabricante,marca_fabricante"),
    "model": _syn("modelo,model"),
    "category": _syn("categoria,category,categoria_produto", "grupo,departamento,familia,linha"),
    "subcategory": _syn("subcategoria,sub_categoria,subgrupo"),
    "supplier": _syn("fornecedor,supplier,nome_fornecedor"),
    "cost_cents": _syn("custo,preco_custo,valor_custo,preco_de_custo,custo_unitario,cost,preco_compra"),
    "price_cents": _syn("preco,preco_venda,valor_venda,preco_de_venda,price,pvenda,preco_unitario,valor_unitario",
                        "valor"),
    "promo_price_cents": _syn("preco_promocional,promocao,valor_promocional,preco_promo,preco_oferta"),
    "stock": _syn("estoque,estoque_atual,stock,saldo_estoque,qtd_estoque", "saldo,quantidade,qtd,qtde,quant"),
    "min_stock": _syn("estoque_minimo,estoque_min,min_stock", "minimo"),
    "unit": _syn("unidade,unidade_medida,unidade_de_medida,un,und,unid"),
    "warranty": _syn("garantia,warranty"),
    "condition": _syn("condicao,condition", "estado"),
    "commercial_status": _syn("status_comercial,situacao", "status,ativo"),
    "description": _syn("descricao_completa,descricao_longa,description,detalhes,descricao_detalhada",
                        "descricao"),
    "technical_description": _syn("descricao_tecnica,ficha_tecnica,especificacao_tecnica,especificacoes_tecnicas"),
    "features": _syn("caracteristicas,beneficios,diferenciais"),
    "material": _syn("material"),
    "color": _syn("cor,color,cores"),
    "weight_kg": _syn("peso_kg,peso_em_kg,peso_bruto_kg,peso_liquido_kg", "peso,peso_bruto,peso_liquido"),
    "weight_g": _syn("peso_g,peso_gramas,peso_em_gramas,peso_gr"),
    "length_cm": _syn("comprimento,comprimento_cm", "profundidade"),
    "width_cm": _syn("largura,largura_cm"),
    "height_cm": _syn("altura,altura_cm"),
    "dimensions_cm": _syn("dimensoes,dimensoes_cm", "medidas"),
    "package_contents": _syn("conteudo_embalagem,itens_inclusos,conteudo_da_embalagem,itens_da_embalagem"),
    "manufacturer_refs": _syn("referencias_fabricante,referencias_cruzadas,codigos_equivalentes,equivalencias"),
    "internal_notes": _syn("observacoes,observacao,obs,notas,observacoes_internas"),
    "images": _syn("imagem,imagens,images,foto,fotos,url_imagem,imagem_url,urls_imagens,link_imagem,imagem_principal",
                   "arquivo,arquivos_imagem,midia"),
    "files": _syn("arquivo_tecnico,manual,datasheet,ficha_pdf,arquivos_tecnicos"),
}

COMPAT_SYNONYMS: dict[str, dict[str, str]] = {
    "sku": _syn("sku,sku_produto,codigo_sku", "codigo,cod_produto,referencia,codigo_produto"),
    "brand": _syn("marca,marca_compativel,montadora,fabricante_veiculo,marca_veiculo", "fabricante"),
    "model": _syn("modelo,modelo_compativel,veiculo,aparelho,equipamento,console"),
    "version": _syn("versao,motor,motorizacao,variante"),
    "year_from": _syn("ano_inicial,ano_de,ano_inicio,de_ano,ano_ini"),
    "year_to": _syn("ano_final,ano_ate,ano_fim,ate_ano,ano_fin"),
    "years": _syn("anos,ano,periodo", "aplicacao_anos"),
    "reference_code": _syn("codigo_referencia,referencia,cod_referencia,codigo_original,codigo_oem,oem"),
    "notes": _syn("observacoes,observacao,obs,notas"),
    "source_detail": _syn("fonte,origem,fonte_informacao"),
}

KNOWN_KEYS: frozenset[str] = frozenset(k for table in (*PRODUCT_SYNONYMS.values(), *COMPAT_SYNONYMS.values())
                                       for k in table)


@dataclass
class ColumnSuggestion:
    column: str
    field: str  # "" = ignore
    confidence: str  # exact | probable | template | none
    reason: str = ""

    @property
    def needs_confirmation(self) -> bool:
        return self.confidence == "probable"


def _synonyms(target: str) -> dict[str, dict[str, str]]:
    return COMPAT_SYNONYMS if target == "compatibility" else PRODUCT_SYNONYMS


def _lookup(key: str, target: str) -> tuple[str, str] | None:
    best: tuple[str, str] | None = None
    for field_key, table in _synonyms(target).items():
        level = table.get(key)
        if level == "exact":
            return field_key, "exact"
        if level == "probable" and best is None:
            best = (field_key, "probable")
    return best


def _numbers(values: list[str]) -> list[float]:
    found = []
    for value in values:
        text = value.strip().replace(".", "").replace(",", ".") if "," in value else value.strip()
        try:
            found.append(float(text))
        except ValueError:
            continue
    return found


def suggest_mapping(headers: list[str], sample: list[dict[str, str]], target: str = "products") -> list[ColumnSuggestion]:
    """One suggestion per column. Single-value fields are used once (first, best match wins)."""
    suggestions: list[ColumnSuggestion] = []
    for column in headers:
        key = normalize_key(column)
        values = [str(row.get(column) or "").strip() for row in sample]
        values = [v for v in values if v]
        hit = _lookup(key, target)
        if hit is None and field_by_key(target, key) is not None and not field_by_key(target, key).multi:
            hit = (key, "exact")  # the column is already named after the field (e.g. MLA's own export)
        if hit is None and target == "products":
            if key.startswith(("spec_", "especificacao_", "esp_")):
                hit = ("spec", "exact")
            elif key.startswith(("atributo_", "attr_")):
                hit = ("attr", "exact")
        if hit is None:
            suggestions.append(ColumnSuggestion(column, IGNORE, "none", "Coluna não reconhecida."))
            continue
        field_key, confidence = hit
        reason = "Nome de coluna conhecido." if confidence == "exact" else "Nome parecido; confirme."
        if target == "products" and field_key == "description" and key == "descricao" and values:
            average = mean(len(v) for v in values)
            if average < 60:
                field_key, reason = "internal_name", f"Textos curtos (média {average:.0f} caracteres): parece o nome."
            else:
                reason = f"Textos longos (média {average:.0f} caracteres): parece a descrição."
        if target == "products" and field_key == "weight_kg" and confidence == "probable":
            numbers = _numbers(values)
            if numbers and all(n == int(n) for n in numbers) and max(numbers) >= 50:
                field_key, reason = "weight_g", "Valores inteiros e altos: parecem gramas."
            elif numbers:
                reason = "Valores pequenos ou com decimais: parecem quilos."
        suggestions.append(ColumnSuggestion(column, field_key, confidence, reason))
    _resolve_conflicts(suggestions, target)
    return suggestions


def _resolve_conflicts(suggestions: list[ColumnSuggestion], target: str) -> None:
    rank = {"template": 0, "exact": 1, "probable": 2}
    owners: dict[str, ColumnSuggestion] = {}
    for s in sorted((s for s in suggestions if s.field), key=lambda s: rank.get(s.confidence, 3)):
        spec = field_by_key(target, s.field)
        if spec is not None and spec.multi:
            continue
        if s.field in owners:
            label = spec.label if spec else s.field
            s.reason = f"{label} já vem da coluna “{owners[s.field].column}”."
            s.field, s.confidence = IGNORE, "none"
        else:
            owners[s.field] = s


def mapping_problems(mapping: dict[str, str], target: str) -> list[str]:
    """Blocking problems of a user mapping (column -> field)."""
    used: dict[str, str] = {}
    problems = []
    for column, key in mapping.items():
        if not key:
            continue
        spec = field_by_key(target, key)
        if spec is None:
            problems.append(f"Campo desconhecido para a coluna “{column}”.")
            continue
        if not spec.multi and key in used:
            problems.append(f"{spec.label} está em duas colunas: “{used[key]}” e “{column}”.")
        used.setdefault(key, column)
    if "sku" not in used:
        problems.append("Escolha a coluna do SKU.")
    if target == "compatibility" and "model" not in used:
        problems.append("Escolha a coluna do modelo compatível.")
    return problems  # a name column is optional: updates by SKU (price, stock) do not need it
