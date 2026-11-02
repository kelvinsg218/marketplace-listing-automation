"""Deterministic product classification into the organization's internal categories.

Testable criteria (no AI, no single-word guesses):
- Evidence: a category PHRASE (2+ words, e.g. "controle remoto") found in the name = 3 points, in the description
  = 1.5; a single WORD in the name = 1, in the description = 0.5. Matches are on whole normalized words, so
  "farol" does not match "faroleiro". Original category text / material / application attributes count as
  description. An EXCLUDE term in name or description disqualifies the category.
- Confidence:
  * "alta": score >= 3, lead over the 2nd category >= 2, and (a phrase in the name or 2+ pieces of evidence);
  * "media" (needs confirmation): score >= 1.5, or a near tie between categories;
  * "baixa": anything else -> not classified. A single isolated word (1 point) never classifies a product.
Manual (confirmed) classifications are never changed by this module; callers skip them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from mla_api.domain.template_inspector import norm

PHRASE_NAME, PHRASE_TEXT, WORD_NAME, WORD_TEXT = 3.0, 1.5, 1.0, 0.5
HIGH_SCORE, HIGH_LEAD, MEDIUM_SCORE = 3.0, 2.0, 1.5
CONTEXT_ATTRIBUTES = ("categoria", "subcategoria", "aplicacao", "material", "tipo", "linha")


@dataclass(frozen=True)
class CategoryRule:
    id: str
    path: str               # "Brinquedos > Veículos de controle remoto"
    phrases: tuple[str, ...]
    words: tuple[str, ...]
    exclude: tuple[str, ...] = ()


@dataclass
class Result:
    category_id: str | None
    path: str | None
    confidence: str          # alta | media | baixa
    score: float
    evidence: list[str] = field(default_factory=list)
    runner_up: str | None = None


def _contains(text: str, term: str) -> bool:
    """Whole-word match; each word also accepts a simple plural ("pastilha" ~ "pastilhas", "farol" ~ "farois"
    is NOT covered: only trailing s/es)."""
    tokens = norm(term).split()
    if not tokens:
        return False
    pattern = r"\s+".join(rf"{re.escape(tok)}(?:e?s)?" for tok in tokens)
    return re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", text) is not None


def classify(name: str, description: str, attributes: dict[str, str], rules: list[CategoryRule]) -> Result:
    n = norm(name)
    extra = " ".join(str(v) for k, v in (attributes or {}).items() if any(c in norm(k) for c in CONTEXT_ATTRIBUTES))
    d = norm(f"{description} {extra}")
    scored: list[tuple[float, CategoryRule, list[str], bool]] = []
    for rule in rules:
        if any(_contains(n, x) or _contains(d, x) for x in rule.exclude):
            continue
        score, evidence, phrase_in_name = 0.0, [], False
        for p in rule.phrases:
            if _contains(n, p):
                score += PHRASE_NAME
                evidence.append(f'expressão "{p}" no nome')
                phrase_in_name = True
            elif _contains(d, p):
                score += PHRASE_TEXT
                evidence.append(f'expressão "{p}" na descrição/atributos')
        for w in rule.words:
            if _contains(n, w):
                score += WORD_NAME
                evidence.append(f'palavra "{w}" no nome')
            elif _contains(d, w):
                score += WORD_TEXT
                evidence.append(f'palavra "{w}" na descrição/atributos')
        if score > 0:
            scored.append((score, rule, evidence, phrase_in_name))
    if not scored:
        return Result(None, None, "baixa", 0.0)
    scored.sort(key=lambda x: (-x[0], x[1].path))
    best, rule, evidence, phrase_in_name = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    runner = scored[1][1].path if len(scored) > 1 else None
    if best >= HIGH_SCORE and best - second >= HIGH_LEAD and (phrase_in_name or len(evidence) >= 2):
        confidence = "alta"
    elif best >= MEDIUM_SCORE:
        confidence = "media"
    else:
        return Result(None, None, "baixa", best, evidence, rule.path)
    return Result(rule.id, rule.path, confidence, best, evidence, runner)


# Starter tree (examples from the product owner; editable per organization, never mandatory).
DEFAULT_TREE: dict[str, dict[str, dict]] = {
    "Brinquedos": {
        "Veículos de controle remoto": {"phrases": ["controle remoto", "carrinho de controle"], "words": ["rc", "drone"]},
        "Bonecos": {"phrases": ["boneco de acao", "action figure"], "words": ["boneco", "boneca"]},
        "Jogos": {"phrases": ["jogo de tabuleiro", "quebra cabeca"], "words": ["jogo", "baralho"],
                  "exclude": ["jogo de chaves", "jogo de pastilhas", "jogo de velas"]},
        "Brinquedos educativos": {"phrases": ["brinquedo educativo", "blocos de montar"], "words": ["educativo", "pedagogico"]},
    },
    "Casa e decoração": {
        "Vasos": {"phrases": ["vaso decorativo", "vaso de planta"], "words": ["vaso", "cachepo"],
                  "exclude": ["vaso sanitario", "vaso de expansao"]},
        "Iluminação": {"phrases": ["luminaria de mesa", "fita de led", "lustre pendente"], "words": ["luminaria", "lustre", "abajur"]},
        "Quadros": {"phrases": ["quadro decorativo", "moldura de quadro"], "words": ["quadro", "moldura"]},
        "Organizadores": {"phrases": ["caixa organizadora", "organizador de gaveta"], "words": ["organizador", "organizadora"]},
    },
    "Autopeças": {
        "Freios": {"phrases": ["pastilha de freio", "disco de freio", "cilindro de freio", "cilindro mestre",
                               "lona de freio", "fluido de freio"], "words": ["freio", "pastilha"]},
        "Motor": {"phrases": ["filtro de oleo", "vela de ignicao", "correia dentada", "junta do cabecote",
                              "bomba de agua"], "words": ["motor", "virabrequim", "pistao"]},
        "Suspensão": {"phrases": ["amortecedor dianteiro", "amortecedor traseiro", "bandeja de suspensao",
                                  "kit batente"], "words": ["amortecedor", "suspensao", "mola"]},
        "Acessórios": {"phrases": ["tapete automotivo", "capa de banco", "palheta limpador"], "words": ["automotivo", "palheta"]},
    },
    "Moda": {
        "Camisetas": {"phrases": ["camiseta manga", "camisa polo"], "words": ["camiseta", "camisa", "regata"]},
        "Calçados": {"phrases": ["tenis de corrida", "sapato social"], "words": ["tenis", "sapato", "sandalia", "bota"],
                     "exclude": ["bota de borracha para motor"]},
        "Acessórios de moda": {"phrases": ["oculos de sol", "bolsa feminina"], "words": ["cinto", "bolsa", "carteira", "bone"]},
    },
}
