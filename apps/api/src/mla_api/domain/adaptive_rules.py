"""Adaptive rules: structured, whitelisted transformations of sheet values, created by form or from a sentence.

Security model:
- A rule is DATA validated against a closed schema (operation + params + condition). Nothing is evaluated:
  no eval/exec, no generated code, no SQL, no regex from users (find/replace is literal).
- Rules target template columns by header text and only writable input columns; helper and formula columns,
  structure and official requirements cannot be changed. After rules run, the template validation still runs, so
  a rule can never make a required/strict-list/length/price requirement pass by itself.
- The natural-language interpreter is deterministic (keyword matching, PT-BR). It only PROPOSES a rule; the user
  reviews a before/after simulation and approves. External AI is not used.

Precedence (later wins): system mapping < organization < account < category < template < batch.
Official template constraints are not rules: they are checked after all rules (validation), always.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from mla_api.domain.template_inspector import PLACEHOLDERS, norm

OPERATIONS = {
    "copy_field": "Copiar valor de um campo do catálogo",
    "set_value": "Usar um valor fixo",
    "default_if_empty": "Valor padrão quando estiver vazio",
    "normalize": "Normalizar texto",
    "truncate": "Limitar quantidade de caracteres",
    "map_value": "Trocar valores (de → para)",
    "prefix": "Adicionar texto antes",
    "suffix": "Adicionar texto depois",
    "replace_text": "Substituir trecho de texto",
    "require": "Exigir preenchimento",
}
NORMALIZE_MODES = ("upper", "lower", "title", "trim", "collapse_spaces")
CONDITIONS = ("always", "target_empty", "field_empty", "field_not_empty", "field_equals", "field_contains")
SCOPES = {"organization": 1, "account": 2, "category": 3, "template": 4, "batch": 5}
MAX_TEXT = 500


class RuleInvalid(ValueError):
    pass


@dataclass(frozen=True)
class RuleDef:
    """Validated rule content (the versioned part)."""
    target: str              # template column header
    operation: str
    params: dict
    condition: dict

    def as_dict(self) -> dict:
        return {"target": self.target, "operation": self.operation, "params": self.params,
                "condition": self.condition}


def _text(params: dict, key: str, required: bool = True, max_len: int = MAX_TEXT) -> str:
    value = params.get(key, "")
    if not isinstance(value, str):
        raise RuleInvalid(f"Parâmetro {key} precisa ser texto.")
    if required and not value.strip():
        raise RuleInvalid(f"Informe {key}.")
    if len(value) > max_len:
        raise RuleInvalid(f"{key} pode ter no máximo {max_len} caracteres.")
    return value


def validate_definition(raw: dict, source_fields: set[str]) -> RuleDef:
    """Closed schema: unknown operations, keys or field names are refused."""
    if not isinstance(raw, dict):
        raise RuleInvalid("Regra inválida.")
    target = _text(raw, "target", max_len=200).strip()
    op = raw.get("operation")
    if op not in OPERATIONS:
        raise RuleInvalid(f"Operação não permitida: {op!r}.")
    params = raw.get("params") or {}
    if not isinstance(params, dict):
        raise RuleInvalid("Parâmetros inválidos.")

    def field_ok(name: str) -> str:
        if name in source_fields or (name.startswith("attr:") and 0 < len(name) - 5 <= 60):
            return name
        raise RuleInvalid(f"Campo do catálogo desconhecido: {name!r}.")

    clean: dict
    if op == "copy_field":
        clean = {"field": field_ok(_text(params, "field", max_len=65))}
    elif op in ("set_value", "default_if_empty", "prefix", "suffix"):
        clean = {"value": _text(params, "value")}
    elif op == "normalize":
        if params.get("mode") not in NORMALIZE_MODES:
            raise RuleInvalid("Modo de normalização inválido.")
        clean = {"mode": params["mode"]}
    elif op == "truncate":
        length = params.get("length")
        if not isinstance(length, int) or not 1 <= length <= 50_000:
            raise RuleInvalid("Informe um limite entre 1 e 50.000 caracteres.")
        clean = {"length": length}
    elif op == "map_value":
        mapping = params.get("map")
        if not isinstance(mapping, dict) or not 1 <= len(mapping) <= 200:
            raise RuleInvalid("Informe de 1 a 200 pares de → para.")
        clean = {"map": {_text({"k": str(k)}, "k"): _text({"v": str(v)}, "v", required=False)
                         for k, v in mapping.items()}}
    elif op == "replace_text":
        clean = {"find": _text(params, "find"), "replace": _text(params, "replace", required=False)}
    else:  # require
        clean = {}
    extra = set(params) - set(clean) - ({"map"} if op == "map_value" else set())
    if extra:
        raise RuleInvalid(f"Parâmetros não permitidos: {sorted(extra)}.")

    cond = raw.get("condition") or {"when": "always"}
    when = cond.get("when", "always")
    if when not in CONDITIONS:
        raise RuleInvalid("Condição inválida.")
    clean_cond: dict = {"when": when}
    if when.startswith("field_"):
        clean_cond["field"] = field_ok(_text(cond, "field", max_len=65))
        if when in ("field_equals", "field_contains"):
            clean_cond["value"] = _text(cond, "value")
    return RuleDef(target=target, operation=op, params=clean, condition=clean_cond)


# --- application --------------------------------------------------------------------------------------------------
@dataclass
class ActiveRule:
    id: str
    version: int
    scope: str
    priority: int
    definition: RuleDef


@dataclass
class Applied:
    values: dict[str, str]
    applied: list[tuple[str, int]] = field(default_factory=list)
    required_missing: list[str] = field(default_factory=list)  # headers from "require" rules


def is_empty(value: object) -> bool:
    return value is None or str(value).strip() == "" or str(value).strip() in PLACEHOLDERS


def ordered(rules: list[ActiveRule]) -> list[ActiveRule]:
    return sorted(rules, key=lambda r: (SCOPES[r.scope], r.priority, r.id))


def apply_rules(values: dict[str, str], rules: list[ActiveRule], resolve) -> Applied:
    """values: {header: current value}; resolve(field) -> catalog value. Rules apply in precedence order."""
    out = Applied(dict(values))
    for rule in ordered(rules):
        d = rule.definition
        header = next((h for h in out.values if norm(h) == norm(d.target)), None)
        if header is None:
            continue
        current = out.values.get(header, "")
        c = d.condition
        when = c["when"]
        if when == "target_empty" and not is_empty(current):
            continue
        if when.startswith("field_"):
            fv = str(resolve(c["field"]) or "")
            if (when == "field_empty" and fv.strip()) or (when == "field_not_empty" and not fv.strip()):
                continue
            if when == "field_equals" and norm(fv) != norm(c["value"]):
                continue
            if when == "field_contains" and norm(c["value"]) not in norm(fv):
                continue
        p, new = d.params, current
        if d.operation == "copy_field":
            v = str(resolve(p["field"]) or "")
            new = v if v.strip() else current
        elif d.operation == "set_value":
            new = p["value"]
        elif d.operation == "default_if_empty":
            new = p["value"] if is_empty(current) else current
        elif d.operation == "normalize" and not is_empty(current):
            s = str(current)
            new = {"upper": s.upper(), "lower": s.lower(), "title": s.title(), "trim": s.strip(),
                   "collapse_spaces": re.sub(r"\s+", " ", s).strip()}[p["mode"]]
        elif d.operation == "truncate" and not is_empty(current):
            new = str(current)[:p["length"]].rstrip()
        elif d.operation == "map_value" and not is_empty(current):
            key = next((k for k in p["map"] if norm(k) == norm(current)), None)
            new = p["map"][key] if key is not None else current
        elif d.operation in ("prefix", "suffix") and not is_empty(current):
            new = p["value"] + str(current) if d.operation == "prefix" else str(current) + p["value"]
        elif d.operation == "replace_text" and not is_empty(current):
            new = str(current).replace(p["find"], p["replace"])
        elif d.operation == "require":
            if is_empty(current):
                out.required_missing.append(header)
            out.applied.append((rule.id, rule.version))
            continue
        if new != current:
            out.values[header] = new
        out.applied.append((rule.id, rule.version))
    return out


def official_conflict(d: RuleDef, spec: dict | None) -> str | None:
    """A rule may not target non-input columns nor force a value the official file forbids."""
    if spec is None:
        return f'A coluna "{d.target}" não existe nesta aba do template.'
    if not spec.get("writable"):
        return f'"{d.target}" é uma coluna calculada/auxiliar do arquivo oficial e não pode ser alterada.'
    value = d.params.get("value")
    if value is not None and d.operation in ("set_value", "default_if_empty"):
        if spec.get("strict") and spec.get("options") and value not in spec["options"]:
            return (f'"{value}" não está na lista oficial de "{d.target}". Opções aceitas: '
                    + ", ".join(o for o in spec["options"] if o not in PLACEHOLDERS)[:300])
        if spec.get("max_length") and len(value) > spec["max_length"]:
            return f'O valor excede o limite oficial de {spec["max_length"]} caracteres de "{d.target}".'
    if d.operation == "truncate" and spec.get("max_length") and d.params["length"] > spec["max_length"]:
        return f'O limite oficial de "{d.target}" é {spec["max_length"]} caracteres.'
    return None


def conflicts(new: RuleDef, scope: str, scope_ref: str, existing: list[dict]) -> list[str]:
    """Same target + same scope + overlapping 'always' conditions = the newer one would silently win."""
    out = []
    for r in existing:
        d = r["definition"]
        if r["scope"] == scope and r["scope_ref"] == scope_ref and norm(d["target"]) == norm(new.target) \
                and d["condition"].get("when") == new.condition.get("when") == "always" and d["operation"] != "require":
            out.append(f'Já existe a regra "{r["name"]}" para "{new.target}" no mesmo escopo; a de maior prioridade '
                       "prevalece.")
    return out


# --- deterministic natural-language interpretation --------------------------------------------------------------
FIELD_WORDS: list[tuple[str, tuple[str, ...]]] = [
    ("description", ("descricao",)),
    ("brand", ("marca",)),
    ("model", ("modelo",)),
    ("gtin", ("codigo universal", "ean", "gtin", "codigo de barras")),
    ("name", ("titulo", "nome do produto", "nome")),
    ("sku", ("sku",)),
    ("price", ("preco",)),
    ("stock", ("estoque",)),
    ("catalog_code", ("codigo de catalogo",)),
]


@dataclass
class Proposal:
    definition: dict | None
    scope: str
    explanation: str
    questions: list[str]
    confidence: str  # alta | media | baixa


def _quoted(text: str) -> str | None:
    m = re.search(r"[\"“'‘]([^\"”'’]{1,200})[\"”'’]", text)
    return m.group(1) if m else None


def interpret(text: str, headers: list[str], attributes: list[str]) -> Proposal:
    """Turns a request such as "use o fabricante do catálogo no campo Marca quando estiver vazio" into a proposal.
    Never guesses silently: unknown pieces become questions."""
    t = norm(text)
    questions: list[str] = []
    scope = "batch"
    if re.search(r"daqui (para|pra) frente|sempre|todas as vezes|proxim[oa]s lotes|regra padrao|salvar como regra", t):
        scope = "category"
    if re.search(r"so neste lote|somente neste lote|apenas neste lote|so nesta planilha|apenas nesta planilha", t):
        scope = "batch"
    if re.search(r"toda a (empresa|organizacao)|todas as categorias", t):
        scope = "organization"

    # Target column: prefer the header named right after "campo"/"coluna", else the longest header mentioned.
    mentioned = sorted({h for h in headers if norm(h) and re.search(rf"\b{re.escape(norm(h))}\b", t)},
                       key=lambda h: -len(norm(h)))
    target = None
    m = re.search(r"\b(campo|coluna)\s+(?:de\s+|do\s+|da\s+)?(.{1,60})", t)
    if m:
        after = m.group(2)
        target = next((h for h in mentioned if after.startswith(norm(h))), None)
    target = target or (mentioned[0] if len(mentioned) == 1 else None)
    if target is None:
        questions.append("Qual coluna da planilha deve ser ajustada? " + (
            f"Encontrei menções a: {', '.join(mentioned)}." if mentioned else "Não reconheci nenhuma coluna da aba."))

    # Source field: catalog attributes first (e.g. "Fabricante"), then core fields, excluding the target word.
    tnorm = norm(target or "")
    source = None
    for attr in sorted(attributes, key=lambda a: -len(a)):
        if norm(attr) and norm(attr) != tnorm and re.search(rf"\b{re.escape(norm(attr))}\b", t):
            source = f"attr:{attr}"
            break
    if source is None:
        for key, words in FIELD_WORDS:
            if any(re.search(rf"\b{re.escape(w)}\b", t) and w != tnorm for w in words):
                if not (target and any(w == tnorm for w in words)):
                    source = key
                    break

    when = "target_empty" if re.search(r"(estiver|estiverem|for|esta|ficar)\s+(vazi|em branco)|quando faltar", t) \
        else "always"
    literal = _quoted(text)
    definition: dict | None = None
    explanation = ""
    if re.search(r"maiuscul", t):
        definition = {"operation": "normalize", "params": {"mode": "upper"}}
        explanation = "Converter o texto para maiúsculas."
    elif re.search(r"minuscul", t):
        definition = {"operation": "normalize", "params": {"mode": "lower"}}
        explanation = "Converter o texto para minúsculas."
    elif (m2 := re.search(r"(limit\w*|maximo de|ate)\s+(\d{1,5})\s+caracteres", t)):
        definition = {"operation": "truncate", "params": {"length": int(m2.group(2))}}
        explanation = f"Cortar o texto em {m2.group(2)} caracteres."
    elif re.search(r"obrigatori|exigir|exija", t) and not source and not literal:
        definition = {"operation": "require", "params": {}}
        explanation = "Acusar erro quando a coluna estiver vazia."
    elif literal:
        op = "default_if_empty" if when == "target_empty" else "set_value"
        definition = {"operation": op, "params": {"value": literal}}
        explanation = f'Preencher com "{literal}"' + (" quando estiver vazio." if op == "default_if_empty" else ".")
        when = "always"
    elif source:
        definition = {"operation": "copy_field", "params": {"field": source}}
        label = source[5:] if source.startswith("attr:") else source
        explanation = f'Copiar o valor de "{label}" do catálogo' + (" quando a coluna estiver vazia." if
                                                                   when == "target_empty" else ".")
    else:
        questions.append("O que deve ser feito? Ex.: copiar um campo do catálogo, usar um valor fixo entre aspas, "
                         "maiúsculas, limitar caracteres.")
    if definition and target:
        definition = {"target": target, **definition, "condition": {"when": when}}
    else:
        definition = None
    confidence = "alta" if definition and not questions and (mentioned and len(mentioned) <= 2) else \
        "media" if definition else "baixa"
    return Proposal(definition, scope, explanation, questions, confidence)


def parse_error_summary(text: str, headers: list[str]) -> list[dict]:
    """'- Marca\\n- Estoque\\n- Forma de envio' (format of "Resumo de erros", P2 p.5) -> recognized columns.
    Lines that match no column are returned as unrecognized, never guessed."""
    out = []
    for line in re.split(r"[\n;]+|\s-\s", text or ""):
        item = line.strip().lstrip("-•*").strip()
        if not item:
            continue
        match = next((h for h in headers if norm(h) == norm(item)), None) or \
            next((h for h in headers if norm(item) and norm(item) in norm(h)), None)
        out.append({"text": item[:200], "column": match})
    return out
