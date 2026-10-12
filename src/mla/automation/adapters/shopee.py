"""Shopee adapter — NOT integrated yet (roadmap phase 6). See mercadolivre.py."""
from __future__ import annotations

from mla.automation.adapters.pending import PendingIntegrationAdapter
from mla.core.enums import Marketplace


class ShopeeAdapter(PendingIntegrationAdapter):
    marketplace = Marketplace.SHOPEE
    home_url = "https://seller.shopee.com.br/"
    pending_message = ("A integração com o formulário real da Shopee ainda não foi implementada "
                       "(fase 6 do roadmap). Use o marketplace simulado para testar o fluxo.")
