"""Plans and feature flags. Enforcement is OFF in the MVP (see LicenseManager.enforce)."""
from __future__ import annotations

from enum import StrEnum


class Plan(StrEnum):
    TRIAL = "trial"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    BUSINESS = "business"

    @property
    def label(self) -> str:
        return {Plan.TRIAL: "Avaliação", Plan.STARTER: "Starter",
                Plan.PROFESSIONAL: "Professional", Plan.BUSINESS: "Business"}[self]


class Feature(StrEnum):
    MERCADO_LIVRE = "mercadolivre"
    SHOPEE = "shopee"
    GROUPS = "groups"
    BATCH = "batch"
    IMPORT_EXPORT = "import_export"
    REPORTS = "reports"
    MULTI_ACCOUNT = "multi_account"
    MULTI_CATALOG = "multi_catalog"
    WORKSPACES = "workspaces"

    @property
    def label(self) -> str:
        return {
            Feature.MERCADO_LIVRE: "Mercado Livre", Feature.SHOPEE: "Shopee", Feature.GROUPS: "Grupos",
            Feature.BATCH: "Execução em lote", Feature.IMPORT_EXPORT: "Importação e exportação",
            Feature.REPORTS: "Relatórios", Feature.MULTI_ACCOUNT: "Múltiplas contas",
            Feature.MULTI_CATALOG: "Múltiplos catálogos", Feature.WORKSPACES: "Espaços de trabalho",
        }[self]


_STARTER = {Feature.MERCADO_LIVRE}
_PROFESSIONAL = _STARTER | {Feature.SHOPEE, Feature.GROUPS, Feature.BATCH, Feature.IMPORT_EXPORT, Feature.REPORTS}
_BUSINESS = _PROFESSIONAL | {Feature.MULTI_ACCOUNT, Feature.MULTI_CATALOG, Feature.WORKSPACES}

PLAN_FEATURES: dict[Plan, frozenset[Feature]] = {
    Plan.TRIAL: frozenset(_BUSINESS),  # trial shows everything
    Plan.STARTER: frozenset(_STARTER),
    Plan.PROFESSIONAL: frozenset(_PROFESSIONAL),
    Plan.BUSINESS: frozenset(_BUSINESS),
}
