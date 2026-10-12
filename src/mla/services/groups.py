from __future__ import annotations

from dataclasses import dataclass, field

from mla.core.enums import Marketplace
from mla.core.models import ProductGroup
from mla.core.validation import validate_product
from mla.persistence.repositories import GroupRepository, ProductRepository


@dataclass
class GroupValidation:
    ready: list[int] = field(default_factory=list)
    blocked: dict[int, list[str]] = field(default_factory=dict)  # product_id -> messages

    @property
    def ok(self) -> bool:
        return bool(self.ready) and not self.blocked


class GroupService:
    def __init__(self, groups: GroupRepository, products: ProductRepository):
        self.groups = groups
        self.products = products

    def list(self) -> list[ProductGroup]:
        return self.groups.list()

    def get(self, group_id: int) -> ProductGroup | None:
        return self.groups.get(group_id)

    def save(self, group: ProductGroup) -> ProductGroup:
        group.name = group.name.strip()
        if not group.name:
            raise ValueError("Dê um nome ao grupo.")
        self.groups.save(group)
        return group

    def delete(self, group_id: int) -> None:
        self.groups.delete(group_id)

    def add_products(self, group_id: int, product_ids: list[int]) -> ProductGroup:
        group = self._require(group_id)
        group.product_ids = list(dict.fromkeys([*group.product_ids, *product_ids]))
        return self.save(group)

    def remove_products(self, group_id: int, product_ids: list[int]) -> ProductGroup:
        group = self._require(group_id)
        drop = set(product_ids)
        group.product_ids = [pid for pid in group.product_ids if pid not in drop]
        return self.save(group)

    def move(self, group_id: int, product_id: int, offset: int) -> ProductGroup:
        group = self._require(group_id)
        ids = group.product_ids
        if product_id not in ids:
            return group
        old = ids.index(product_id)
        new = max(0, min(len(ids) - 1, old + offset))
        ids.insert(new, ids.pop(old))
        return self.save(group)

    def validate(self, group_id: int, marketplaces: list[Marketplace] | None = None) -> GroupValidation:
        group = self._require(group_id)
        targets = marketplaces or group.marketplaces
        result = GroupValidation()
        if not targets:
            result.blocked[0] = ["Selecione ao menos um marketplace para o grupo."]
            return result
        for pid in group.product_ids:
            product = self.products.get(pid)
            if product is None:
                continue
            report = validate_product(product)
            messages = []
            for marketplace in targets:
                messages += [f"{marketplace.label}: {i.message}" if i.marketplace else i.message
                             for i in report.errors(marketplace)]
            messages = list(dict.fromkeys(messages))
            if messages:
                result.blocked[pid] = messages
            else:
                result.ready.append(pid)
        return result

    def _require(self, group_id: int) -> ProductGroup:
        group = self.groups.get(group_id)
        if group is None:
            raise ValueError("Grupo não encontrado.")
        return group
