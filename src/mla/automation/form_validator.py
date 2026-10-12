"""Compare what the adapter typed into the form with what the catalog says."""
from __future__ import annotations

import re
from dataclasses import dataclass

from mla.automation.base import ListingPayload
from mla.core.units import ParseError, parse_money


@dataclass(frozen=True)
class Mismatch:
    field: str
    expected: str
    found: str

    def __str__(self) -> str:
        return f"{self.field}: esperado '{self.expected}', encontrado '{self.found}'"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


class FormValidator:
    @staticmethod
    def compare(payload: ListingPayload, form: dict[str, str]) -> list[Mismatch]:
        problems: list[Mismatch] = []
        if "title" in form and _norm(form["title"]) != _norm(payload.title):
            problems.append(Mismatch("Título", payload.title, form["title"]))
        if "price" in form:
            try:
                found = parse_money(form["price"])
            except ParseError:
                found = None
            if found != payload.price_cents:
                problems.append(Mismatch("Preço", payload.price_text, form["price"]))
        if "stock" in form and str(form["stock"]).strip() != str(payload.stock):
            problems.append(Mismatch("Estoque", str(payload.stock), str(form["stock"])))
        if "description" in form and _norm(form["description"]) != _norm(payload.description):
            problems.append(Mismatch("Descrição", f"{len(payload.description)} caracteres",
                                     f"{len(form['description'])} caracteres"))
        if "images" in form and int(form["images"] or 0) != len(payload.images):
            problems.append(Mismatch("Imagens", str(len(payload.images)), str(form["images"])))
        return problems
