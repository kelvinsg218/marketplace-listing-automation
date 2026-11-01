"""SYNTHETIC workbook that imitates the layout visible in the official help captures (P2 p.2/p.4, P3 p.4).

It is NOT an official Mercado Livre template. Tests built on it check MLA's own logic (inspection, mapping,
isolation); they prove nothing about compatibility with the real Anunciador em massa.
"""
from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.worksheet.datavalidation import DataValidation

HEADERS = ["Código do catálogo ML", "Título", "SKU", "Preço", "Estoque", "Marca", "Fotos", "Resumo de erros"]


def build(deadline_text: str = "Faça isso até 10 de setembro", hidden_sheet: bool = True,
          with_help: bool = True) -> bytes:
    wb = Workbook()
    help_ws = wb.active
    if with_help:
        help_ws.title = "Ajuda"
        help_ws["A1"] = "Anuncie vários produtos de uma vez"
        help_ws["A5"] = "Enviar planilha"
        help_ws["A6"] = deadline_text
        help_ws["C2"] = "1. Como é a estrutura da planilha Excel?"
        ws = wb.create_sheet("Biscoitos")
    else:
        ws = help_ws
        ws.title = "Biscoitos"
    ws["A1"] = "Alimentos e bebidas > Biscoitos"
    ws["A2"] = "Biscoitos"
    for c, h in enumerate(HEADERS, start=1):
        ws.cell(3, c, h)
    for col in ("B", "D", "G"):  # "Obrigatório" right below the header, as in the captures
        ws[f"{col}4"] = "Obrigatório"
    ws["E5"] = "Para catálogo, não é necessário preencher este dado."
    ws["H6"] = '=IF(B7="","- Título","")'
    dv = DataValidation(type="list", formula1='"Lista geral,Catálogo"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add("A7:A500")
    if hidden_sheet:
        hidden = wb.create_sheet("listas")
        hidden["A1"] = "Lista geral"
        hidden.sheet_state = "hidden"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


OFFICIAL_HEADERS = ["Título: informe o produto, marca, modelo e destaque as características principais",
                    "Quantidade de caracteres", "Condição", "Fotos", "SKU", "Estoque", "Preço [R$]", "Descrição",
                    "Tipo de anúncio", "Forma de envio", "Varia por: Tamanho", "Marca", "Número de peça",
                    "BUYBOX_FORMULA", "HIDDEN_PICTURES"]
REQUIRED = {"A", "C", "D", "F", "G", "I", "J", "L", "M"}


def build_official_like(rows: int = 20, fake_binding: str = "0000000000-bulk-sell-aaaaaaaaaaaa") -> bytes:
    """SYNTHETIC workbook that mirrors the layout of a REAL template analysed on 2026-11-01
    (docs/MLA_OFFICIAL_TEMPLATE_ANALYSIS.md): Ajuda with the deadline, very hidden list sheet with a (fake)
    binding row, header row 3, "Obrigatório" row 4, help row 5, links row 6, data from row 7 with defaults and
    formulas, helper columns, list validations pointing at the hidden sheet, title/price conditional formatting.
    No value comes from a real file."""
    from openpyxl.formatting.rule import FormulaRule
    wb = Workbook()
    ajuda = wb.active
    ajuda.title = "Ajuda"
    ajuda["B1"] = "Ajuda para preencher a planilha"
    ajuda["C26"] = "Faça isso antes de 1 de dezembro"
    extra = wb.create_sheet("extra info")
    extra.sheet_state = "veryHidden"
    extra["A1"], extra["B1"], extra["C1"] = fake_binding, "2099-12-01", "00000000-0000-4000-8000-000000000000"
    for c, v in enumerate(["Novo", "Usado"], 1):
        extra.cell(2, c, v)
    for c, v in enumerate(["Premium", "Clássico"], 1):
        extra.cell(3, c, v)
    extra.cell(4, 1, "Mercado Envios")
    for c, v in enumerate(["Insira ou selecione um valor", "P", "M", "G"], 1):
        extra.cell(5, c, v)
    ws = wb.create_sheet("Peças de Teste")
    ws["A1"] = "Acessórios para Veículos > Peças de Teste"
    ws["A2"] = "Peças de Teste"
    for c, h in enumerate(OFFICIAL_HEADERS, 1):
        cell = ws.cell(3, c, h)
        ws.cell(4, c, "Obrigatório" if cell.column_letter in REQUIRED else "")
    ws["A5"] = "Máximo de 60 caracteres."
    ws["D6"] = "Obter URLs no gestor de fotos"
    ws.column_dimensions["N"].hidden = ws.column_dimensions["O"].hidden = True
    last = 6 + rows
    for r in range(7, last + 1):
        ws[f"B{r}"] = "=LEN(INDIRECT(ADDRESS(ROW() + (0),COLUMN() + (-1))))"
        ws[f"C{r}"] = "Novo"
        ws[f"F{r}"] = 1.0
        ws[f"I{r}"] = "Clássico"
        ws[f"J{r}"] = "Mercado Envios"
        ws[f"K{r}"] = "Insira ou selecione um valor"
        ws[f"N{r}"] = '=IF(TRIM(INDIRECT("A"&ROW())) <> "",FALSE,"")'
    for col, src, strict in (("C", "$A$2:$B$2", True), ("I", "$A$3:$B$3", True), ("J", "$A$4:$A$4", True),
                             ("K", "$A$5:$D$5", False)):
        dv = DataValidation(type="list", formula1=f"'extra info'!{src}", allow_blank=True, showErrorMessage=strict)
        ws.add_data_validation(dv)
        dv.add(f"{col}7:{col}10001")
    for col, kind, f1 in (("E", "textLength", "255"), ("F", "decimal", "0.0"), ("G", "decimal", "0.0"),
                          ("L", "textLength", "255")):
        dv = DataValidation(type=kind, operator="lessThanOrEqual" if kind == "textLength" else "greaterThanOrEqual",
                            formula1=f1, allow_blank=True)
        ws.add_data_validation(dv)
        dv.add(f"{col}7:{col}10001")
    ws.conditional_formatting.add(f"A7:A{last}", FormulaRule(formula=["LEN(INDIRECT(ADDRESS(ROW(),COLUMN()))) > 60"]))
    ws.conditional_formatting.add(f"G7:G{last}", FormulaRule(
        formula=['AND(TRIM($N7) <> "",OR(TRIM($G7) = "",$G7 = "",$G7 < 8.00,ISTEXT($G7)))']))
    legal = wb.create_sheet("Informações legais")
    legal["B3"] = "Produtos que estão proibidos no Mercado Livre"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
