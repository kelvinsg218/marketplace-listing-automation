from __future__ import annotations

from mla.automation.adapters.mercadolivre import MercadoLivreAdapter
from mla.automation.adapters.shopee import ShopeeAdapter
from mla.automation.adapters.simulated import SimulatedMarketplaceAdapter
from mla.automation.base import BaseMarketplaceAdapter
from mla.core.enums import Marketplace

ADAPTERS: dict[Marketplace, type[BaseMarketplaceAdapter]] = {
    Marketplace.MERCADO_LIVRE: MercadoLivreAdapter,
    Marketplace.SHOPEE: ShopeeAdapter,
    Marketplace.SIMULATED: SimulatedMarketplaceAdapter,
}


def adapter_for(marketplace: Marketplace) -> type[BaseMarketplaceAdapter]:
    return ADAPTERS[marketplace]
