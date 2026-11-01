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
