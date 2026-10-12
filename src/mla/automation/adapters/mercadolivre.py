"""Mercado Livre adapter — NOT integrated yet (roadmap phase 4).

The real seller form has not been inspected with an authorised account, so no
selectors are guessed. Phase 4: inspect the form (Chrome DevTools MCP), then
implement the steps of BaseMarketplaceAdapter here and set implemented = True.
"""
from __future__ import annotations

from mla.automation.adapters.pending import PendingIntegrationAdapter
from mla.core.enums import Marketplace


class MercadoLivreAdapter(PendingIntegrationAdapter):
    marketplace = Marketplace.MERCADO_LIVRE
    home_url = "https://www.mercadolivre.com.br/"
    pending_message = ("A integração com o formulário real do Mercado Livre ainda não foi implementada "
                       "(fase 4 do roadmap). Use o marketplace simulado para testar o fluxo.")
