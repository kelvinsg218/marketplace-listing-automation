"""Loads the adaptive rules that apply to a batch (always within one organization)."""
from __future__ import annotations

import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from mla_api.domain.adaptive_rules import ActiveRule, RuleDef
from mla_api.models import ListingBatch, ListingRule, ListingRuleVersion


def rules_for_batch(db: Session, org_id: uuid.UUID, batch: ListingBatch) -> list[ActiveRule]:
    scopes = [ListingRule.scope == "organization",
              and_(ListingRule.scope == "batch", ListingRule.scope_ref == str(batch.id))]
    if batch.seller_account_id:
        scopes.append(and_(ListingRule.scope == "account", ListingRule.scope_ref == str(batch.seller_account_id)))
    if batch.template_id:
        scopes.append(and_(ListingRule.scope == "template", ListingRule.scope_ref == str(batch.template_id)))
    if batch.sheet_name:
        scopes.append(and_(ListingRule.scope == "category", ListingRule.scope_ref == batch.sheet_name))
    rows = db.execute(
        select(ListingRule, ListingRuleVersion)
        .join(ListingRuleVersion, and_(ListingRuleVersion.rule_id == ListingRule.id,
                                       ListingRuleVersion.version == ListingRule.current_version))
        .where(ListingRule.organization_id == org_id, ListingRule.status == "active", or_(*scopes))).all()
    return [ActiveRule(str(r.id), v.version, r.scope, r.priority, RuleDef(**v.definition)) for r, v in rows]
